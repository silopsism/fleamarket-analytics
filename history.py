"""Prior-season rates, kept separately from the live API.

bootstrap-static carries only the CURRENT season's stats. At the season rollover
FPL zeroes every one of them - minutes, goals, xG, xA, defensive contributions -
and our model, which reads those fields as prior-season rates, has nothing left
to stand on. It happened at 2026/27's first deadline and broke the model outright.

So the prior season is snapshotted here, keyed by `code` - FPL's player id is
reassigned between seasons, `code` is not - and merged back over the live data.

merge() also handles the rest of the season: as real minutes accumulate, weight
shifts from last season's rates to this season's, reaching all-current at
BLEND_MINUTES. It returns ONE consistent synthetic season, so every downstream
`stat / (minutes / 90)` recovers exactly the blended per-90 rate with no changes
elsewhere.

    python history.py build bootstrap_old.json 2025/26     # snapshot a season
    python history.py check                                # coverage report
"""
import json
import os

PATH = 'history.json'
BLEND_MINUTES = 900        # a full-ish sample: at this point the new season wins

# counting stats: totals over a season, used to form per-90 rates
COUNTS = ('minutes', 'starts', 'goals_scored', 'assists', 'clean_sheets', 'saves',
          'bonus', 'bps', 'yellow_cards', 'red_cards', 'goals_conceded',
          'own_goals', 'penalties_saved', 'penalties_missed',
          'defensive_contribution', 'total_points')
# already per-90, so they blend directly
RATES = ('expected_goals_per_90', 'expected_assists_per_90',
         'expected_goal_involvements_per_90', 'expected_goals_conceded_per_90',
         'saves_per_90', 'starts_per_90', 'clean_sheets_per_90')
# season totals that behave like counts but are stored as strings
FLOAT_COUNTS = ('expected_goals', 'expected_assists', 'expected_goal_involvements',
                'expected_goals_conceded')


def build(src='bootstrap_old.json', season='2025/26', out=PATH):
    """Snapshot a bootstrap's stats as the prior season, keyed by code."""
    d = json.load(open(src, encoding='utf-8'))
    teams = {t['id']: t['short_name'] for t in d['teams']}
    rows = {}
    for e in d['elements']:
        rec = {'name': e['web_name'], 'club': teams.get(e['team'], '?'),
               'pos': e['element_type']}
        for f in COUNTS:
            rec[f] = e.get(f) or 0
        for f in RATES + FLOAT_COUNTS:
            try:
                rec[f] = float(e.get(f) or 0)
            except (TypeError, ValueError):
                rec[f] = 0.0
        rows[str(e['code'])] = rec
    payload = {'season': season, 'source': src, 'players': rows}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    return payload


def load(path=PATH):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _per90(total, minutes):
    return (total / (minutes / 90)) if minutes else 0.0


def merge(d, hist=None, blend_minutes=BLEND_MINUTES, path=PATH):
    """Blend prior-season rates into the live bootstrap, in place.

    Returns meta about what happened. Identity and market fields (price, status,
    news, ownership, team) always come from the live data - only the statistical
    history is blended, because that is the only part the rollover destroys.
    """
    hist = hist if hist is not None else load(path)
    if not hist or not hist.get('players'):
        return {'merged': 0, 'reason': 'no history file'}
    rows = hist['players']
    played = sum(1 for e in d.get('events', []) if e.get('finished'))
    scale = (38 / played) if played else 0.0     # full-season-equivalent

    merged = no_hist = 0
    for e in d['elements']:
        h = rows.get(str(e.get('code')))
        if not h:
            no_hist += 1
            continue
        cur_min = e.get('minutes') or 0
        w = min(cur_min / blend_minutes, 1.0) if blend_minutes else 1.0

        # one synthetic season's worth of minutes: last season's, giving way to
        # this season's projected to a full 38 games
        eff_min = (1 - w) * h['minutes'] + w * (cur_min * scale)
        if eff_min <= 0:
            eff_min = float(cur_min or h['minutes'])

        for f in COUNTS + FLOAT_COUNTS:
            if f == 'minutes':
                continue
            prev90 = _per90(h.get(f, 0), h['minutes'])
            cur90 = _per90(float(e.get(f) or 0), cur_min)
            blended90 = w * cur90 + (1 - w) * prev90
            val = blended90 * eff_min / 90
            e[f] = val if f in FLOAT_COUNTS else (int(round(val)) if f != 'starts'
                                                  else int(round(val)))
        for f in RATES:
            try:
                cur = float(e.get(f) or 0)
            except (TypeError, ValueError):
                cur = 0.0
            e[f] = w * cur + (1 - w) * h.get(f, 0.0)
        e['minutes'] = int(round(eff_min))
        e['_hist_w'] = round(w, 3)
        merged += 1

    return {'merged': merged, 'no_history': no_hist, 'season': hist.get('season'),
            'games_played': played, 'blend_minutes': blend_minutes}


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'build':
        src = sys.argv[2] if len(sys.argv) > 2 else 'bootstrap_old.json'
        season = sys.argv[3] if len(sys.argv) > 3 else '2025/26'
        p = build(src, season)
        tot = sum(r['minutes'] for r in p['players'].values())
        print(f"{PATH}: {len(p['players'])} players from {src} ({season}), "
              f"{tot:,} minutes, {os.path.getsize(PATH)/1024:.0f}KB")
    else:
        h = load()
        d = json.load(open('bootstrap.json', encoding='utf-8'))
        if not h:
            raise SystemExit('no history.json - run: python history.py build')
        have = sum(1 for e in d['elements'] if str(e.get('code')) in h['players'])
        print(f"history {h['season']}: {len(h['players'])} players")
        print(f"current bootstrap: {len(d['elements'])} players, {have} with history, "
              f"{len(d['elements']) - have} without")
        print('merge ->', merge(d, h))
        hl = next((e for e in d['elements'] if e['web_name'] == 'Haaland'), None)
        if hl:
            print(f"  Haaland after merge: mins={hl['minutes']} starts={hl['starts']} "
                  f"G={hl['goals_scored']} xG90={hl['expected_goals_per_90']:.3f} "
                  f"w={hl['_hist_w']}")
