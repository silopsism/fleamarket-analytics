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


def expected_minutes(d):
    teams = {t['id']: t['short_name'] for t in d['teams']}
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

    out = {}
    for e in d['elements']:
        okey = f"{e['web_name']}|{teams[e['team']]}"
        base = min(e['minutes'] / 38, CAP)
        src = f'last season ({e["starts"]} starts)'

        # injury regression: a currently-fit player's past absences are only
        # partially predictive, so regress availability toward a healthy
        # baseline, floored at actual so durable players aren't dragged down.
        # Eligibility is a STARTER'S PROFILE (they finish the games they start),
        # not a minutes total — the old >=1000-minute gate excluded exactly the
        # injury-wrecked players who need this most.
        mps = e['minutes'] / e['starts'] if e['starts'] else 0
        starter_shape = e['starts'] >= 5 and 70 <= mps <= 95
        if e['status'] == 'a' and (starter_shape
                                   or (e['minutes'] >= 1000 and e['starts'] >= 10)):
            avail = e['minutes'] / (38 * 90)
            adj = max(avail, 0.55 * avail + 0.45 * 0.88)
            cand = min(adj * min(mps or 90, 90), CAP)
            if cand > base:
                base = cand
                src = f'last season, injury-regressed ({avail:.0%}→{adj:.0%} avail)'

        if e['element_type'] == 1:
            if gk_best[e['team']][1] == e['id'] and e['now_cost'] >= 40:
                if base < 60:
                    base, src = 85.0, 'club #1 keeper by price'
            else:
                base, src = min(base, 5.0), 'backup keeper'
        else:
            sel = float(e['selected_by_percent'])
            m = med.get((e['element_type'], round(e['now_cost'] / 5)), 1.0)
            if sel >= 8 and sel > 3 * max(m, 0.5) and base < 65:
                base, src = 75.0, f'crowd signal ({sel:.0f}% owned vs {m:.1f}% typical)'

        ramp = None
        if okey in over:
            o = over[okey]
            # a ramp is one xmins per horizon gameweek, for a player whose
            # minutes are climbing back rather than sitting flat: a new signing
            # bedding in, someone short of pre-season, a return from injury.
            # Flat 'xmins' stays the common case.
            if o.get('ramp'):
                ramp = [float(v) for v in o['ramp']]
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
