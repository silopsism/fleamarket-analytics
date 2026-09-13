"""Expected-minutes subsystem.

expected_minutes(bootstrap) -> {element_id: {'xmins': float, 'src': str}}

Signal precedence:
  1. xmins_overrides.json  (curated, verified facts)
  2. FPL availability      (status + chance_of_playing -> scaling / zero)
  3. GK depth rule         (top-priced keeper per club = intended #1)
  4. Crowd signal          (outfielders: ownership far above price-band peers
                            implies the community expects them to start)
  5. Last-season baseline  (minutes per team-game)

Run directly for the crowd-vs-model discrepancy report (the weekly human
review list).
"""
import json
import os
from collections import defaultdict

CAP = 92.0
# How much real football has to sit behind a minutes estimate before it is
# allowed to stand on its own, and what it is pulled toward until then. One
# 90-minute start proves a player CAN start, not that he starts every week -
# but e['minutes'] is a full-season equivalent, so it arrives claiming 90 a game
# with the same confidence as a player who did it 38 times.
EVIDENCE_MINUTES = 900          # ~10 full games
NEUTRAL_MINUTES = 45.0          # a squad player: in some weeks, out others


def expected_minutes(d):
    teams = {t['id']: t['short_name'] for t in d['teams']}
    # Which gameweek the projection horizon starts at. A ramp names specific
    # gameweeks, so it has to be anchored to one; without this the list is read
    # positionally and a ramp written for GW1-4 quietly becomes GW3-6, holding a
    # settled player at his first-week integration minutes forever.
    nxt = next((ev['id'] for ev in d.get('events', []) if ev.get('is_next')), None)
    if nxt is None:
        nxt = next((ev['id'] for ev in d.get('events', [])
                    if not ev.get('finished')), 1)
    over = {}
    if os.path.exists('xmins_overrides.json'):
        raw = json.load(open('xmins_overrides.json', encoding='utf-8'))
        over = {k: v for k, v in raw.items() if not k.startswith('_')}

    # top-priced GK per club (ties broken by last-season minutes)
    gk_best = {}
    for e in d['elements']:
        if e['element_type'] == 1:
            key = e['team']
            cur = gk_best.get(key)
            rank = (e['now_cost'], e['minutes'])
            if cur is None or rank > cur[0]:
                gk_best[key] = (rank, e['id'])

    # ownership medians per (position, price bucket) for the crowd signal
    buckets = defaultdict(list)
    for e in d['elements']:
        buckets[(e['element_type'], round(e['now_cost'] / 5))].append(
            float(e['selected_by_percent']))
    med = {k: sorted(v)[len(v) // 2] for k, v in buckets.items()}

    # Observed starts: who this manager has actually been picking. Two signals
    # decide a lineup - fitness, and whether he has been starting LATELY - and
    # recency is what separates a favoured starter from a rotation option
    # without having to model rotation at all.
    starts, club_gws = {}, {}
    try:
        import lineups
        done = sorted(ev['id'] for ev in d.get('events', []) if ev.get('finished'))
        if done:
            starts = lineups.fetch(done)
            fx = json.load(open('fixtures.json', encoding='utf-8'))
            for f in fx:
                if f.get('finished') and f.get('event'):
                    for t in (f['team_h'], f['team_a']):
                        club_gws.setdefault(t, set()).add(f['event'])
    except Exception as exc:  # noqa: BLE001 - fall back to the season baseline
        print('minutes: start history unavailable:', exc)

    out = {}
    for e in d['elements']:
        okey = f"{e['web_name']}|{teams[e['team']]}"
        base = min(e['minutes'] / 38, CAP)
        src = f'last season ({e["starts"]:.0f} starts)'

        # injury regression: a currently-fit player's past absences are only
        # partially predictive, so regress availability toward a healthy
        # baseline, floored at actual so durable players aren't dragged down.
        # Eligibility is a STARTER'S PROFILE (they finish the games they start),
        # not a minutes total — the old >=1000-minute gate excluded exactly the
        # injury-wrecked players who need this most.
        mps = e['minutes'] / e['starts'] if e['starts'] else 0
        # Judge "is he a starter?" on starts actually made. e['starts'] is a
        # full-season equivalent, so a player who started once this season
        # arrives here claiming 38 - which read as a nailed starter and handed
        # every one-game player 90 expected minutes.
        ev_starts = e.get('_real_starts', e['starts'])
        starter_shape = ev_starts >= 5 and 70 <= mps <= 95
        if e['status'] == 'a' and (starter_shape
                                   or (e.get('_real_minutes', e['minutes']) >= 1000
                                       and ev_starts >= 10)):
            avail = e['minutes'] / (38 * 90)
            adj = max(avail, 0.55 * avail + 0.45 * 0.88)
            cand = min(adj * min(mps or 90, 90), CAP)
            if cand > base:
                base = cand
                src = f'last season, injury-regressed ({avail:.0%}→{adj:.0%} avail)'

        # thin evidence pulls the estimate toward a squad player. Downward only:
        # a genuinely low-minutes player should not be talked up by this.
        ev_mins = e.get('_real_minutes', e['minutes'])
        if okey not in over and 0 <= ev_mins < EVIDENCE_MINUTES:
            c = ev_mins / EVIDENCE_MINUTES
            thin = c * base + (1 - c) * min(base, NEUTRAL_MINUTES)
            if base - thin >= 1:
                src = f'{src}; thin evidence ({ev_mins:.0f} real min)'
            base = thin

        if e['element_type'] == 1:
            if gk_best[e['team']][1] == e['id'] and e['now_cost'] >= 40:
                if base < 60:
                    base, src = 85.0, 'club #1 keeper by price'
            else:
                base, src = min(base, 5.0), 'backup keeper'
        else:
            sel = float(e['selected_by_percent'])
            m = med.get((e['element_type'], round(e['now_cost'] / 5)), 1.0)
            # Ownership is a stand-in for "the community expects him to start",
            # and it is only worth listening to while nobody has played. Once
            # there are team sheets, they are the better evidence: Will Hughes
            # was 11% owned with zero minutes in two Palace squads, and this
            # rule kept insisting on 75 minutes a week.
            if (sel >= 8 and sel > 3 * max(m, 0.5) and base < 65
                    and not e.get('_club_games')):
                base, src = 75.0, f'crowd signal ({sel:.0f}% owned vs {m:.1f}% typical)'

        # Observed team sheets. Everything above is a pre-season estimate; this
        # is the only part that knows what the manager has actually done.
        gp = e.get('_club_games') or 0
        hist = {g: rows[str(e['id'])] for g, rows in starts.items()
                if str(e['id']) in rows}
        cg = club_gws.get(e['team'], set())
        p_start = weeks = None
        if hist and cg:
            import lineups
            p_start, weeks = lineups.start_probability(e, hist, cg)
        if p_start is not None and weeks >= lineups.MIN_WEEKS:
            # Split the question in two, because they have different answers:
            # how likely is he to start, and how long does he last when he does.
            # A blended minutes-per-club-game average conflates a nailed player
            # who gets subbed with a rotation option who plays ninety when picked.
            played = [m for g, (st, m) in hist.items() if st]
            on_bench = [m for g, (st, m) in hist.items() if not st]
            # never started: there is no "minutes when he starts" to observe, so
            # fall back to the season baseline rather than reporting a number the
            # sample cannot support
            mins_start = min(sum(played) / len(played), CAP) if played else min(base, CAP)
            mins_sub = sum(on_bench) / len(on_bench) if on_bench else 0.0
            base = p_start * mins_start + (1 - p_start) * mins_sub
            src = f'{p_start:.0%} to start over {weeks} gw'
            if played:
                src += f' · {mins_start:.0f} min when he does'
            elif mins_sub:
                src += f' · {mins_sub:.0f} min off the bench'
            else:
                src += ' · has not featured'
        elif gp and e['status'] == 'a':
            # not enough weeks yet: fall back to the crude blend
            obs_mps = min((e.get('_cur_minutes') or 0) / gp, CAP)
            w_obs = min(gp / 5.0, 0.85)
            blended = (1 - w_obs) * base + w_obs * obs_mps
            if abs(blended - base) >= 1:
                src = f'{src}; {gp} played at {obs_mps:.0f}/gm (w={w_obs:.0%})'
            base = blended

        ramp = None
        if okey in over:
            o = over[okey]
            # a ramp is one xmins per horizon gameweek, for a player whose
            # minutes are climbing back rather than sitting flat: a new signing
            # bedding in, someone short of pre-season, a return from injury.
            # Flat 'xmins' stays the common case.
            if o.get('ramp'):
                vals = [float(v) for v in o['ramp']]
                # drop the weeks already played, then hold the final value: a
                # ramp that has run its course means the player has arrived, not
                # that he reverts to the flat average of his climb.
                skip = max(nxt - int(o.get('from', 1)), 0)
                vals = vals[skip:] or [vals[-1]]
                ramp = vals + [vals[-1]] * skip      # keep the horizon length
                base = sum(ramp) / len(ramp)
            else:
                base = float(o['xmins'])
            src = f"override: {o['reason']}"
        # availability scaling always applies on top
        chance = e['chance_of_playing_next_round']
        if e['status'] in ('i', 'u', 'n', 's') and (chance is None or chance == 0):
            base, ramp, src = 0.0, None, f"unavailable ({e['status']}): {e['news'][:40]}"
        elif chance is not None and chance < 100:
            base *= chance / 100
            if ramp:
                ramp = [v * chance / 100 for v in ramp]
            src += f' × {chance}% fit'

        out[e['id']] = {'xmins': min(base, CAP), 'src': src,
                        'ramp': [min(v, CAP) for v in ramp] if ramp else None,
                        'trust': bool(over.get(okey, {}).get('trust_rates')),
                        # for a player with no PL record, how much better (or
                        # worse) than the typical player of his price we judge
                        # him to be - pre-season form is the usual reason
                        'prior_mult': float(over.get(okey, {}).get('prior_mult') or 1.0)}
    return out


if __name__ == '__main__':
    d = json.load(open('bootstrap.json', encoding='utf-8'))
    teams = {t['id']: t['short_name'] for t in d['teams']}
    xm = expected_minutes(d)
    print('=== DISCREPANCY REPORT: crowd vs minutes model (review these) ===')
    rows = []
    for e in d['elements']:
        sel = float(e['selected_by_percent'])
        m = xm[e['id']]['xmins']
        if sel >= 4 and m < 50:  # crowd owns him, model says he barely plays
            rows.append((sel, e['web_name'], teams[e['team']], m, xm[e['id']]['src']))
    for sel, n, t, m, src in sorted(rows, reverse=True)[:15]:
        print(f'{sel:5.1f}% owned  {n:18} {t:4} xmins={m:4.0f}  ({src})')
    print()
    print('=== APPLIED SIGNALS (non-baseline) ===')
    for e in d['elements']:
        s = xm[e['id']]['src']
        if s.startswith(('override', 'crowd', 'club #1')) and float(e['selected_by_percent']) > 3:
            print(f"{e['web_name']:18} {teams[e['team']]:4} xmins={xm[e['id']]['xmins']:4.0f}  {s}")
