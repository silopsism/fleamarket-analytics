"""Phase 1 xPts model: prior-season Opta rates (from FPL API) -> per-match
expected points, then LP squad optimization.

xPts/match = appearance + goals(xG90) + assists(xA90) + clean sheets
           + saves + defcon + bonus, fixture-adjusted over GW1-4.
Minutes: last-season mins/38 by default, with overrides for verified role
changes (the FPL Review 'editable xMins' pattern). New-to-PL (<400 mins):
price-based prior with a regression haircut.
"""
import json
import math
from collections import defaultdict
import pulp

HORIZON = 4          # gameweeks for fixture adjustment
GOAL_VAL = {1: 10, 2: 6, 3: 5, 4: 4}
CS_VAL = {1: 4, 2: 4, 3: 1, 4: 0}
DEFCON_THRESH = {2: 10, 3: 12, 4: 12}
# verified role changes: expected minutes per match (team news, predicted XIs)
XMINS_OVERRIDE = {
    ('Kinsky', 'TOT'): 88, ('Lammens', 'MUN'): 88, ('Dubravka', 'TOT'): 0,
    ('Roefs', 'SUN'): 88, ('Woltemade', 'NEW'): 70,
}

d = json.load(open('bootstrap.json', encoding='utf-8'))
fx = json.load(open('fixtures.json', encoding='utf-8'))
teams = {t['id']: t['short_name'] for t in d['teams']}
pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

# fixture difficulty per team over horizon
fdr = defaultdict(list)
for f in fx:
    if f['event'] and f['event'] <= HORIZON:
        fdr[f['team_h']].append(f['team_h_difficulty'])
        fdr[f['team_a']].append(f['team_a_difficulty'])
avg_fdr = {t: sum(v) / len(v) for t, v in fdr.items()}

# team defensive context: minutes-weighted mean xGC/90 of current squad members
# with >900 prior-season minutes (movers inherit their new club's context)
tw = defaultdict(lambda: [0.0, 0.0])
for e in d['elements']:
    if e['minutes'] > 900 and float(e['expected_goals_conceded_per_90']) > 0:
        tw[e['team']][0] += float(e['expected_goals_conceded_per_90']) * e['minutes']
        tw[e['team']][1] += e['minutes']
team_xgc90 = {t: (v[0] / v[1] if v[1] else 1.4) for t, v in tw.items()}
for t in teams:
    team_xgc90.setdefault(t, 1.7)  # promoted sides with no data: weak prior

players = []
for e in d['elements']:
    if e['status'] in ('i', 'u', 'n', 's'):
        continue
    chance = e['chance_of_playing_next_round']
    avail = (chance / 100) if chance is not None else 1.0
    price = e['now_cost'] / 10
    pos = e['element_type']
    key = (e['web_name'], teams[e['team']])
    mins, starts = e['minutes'], e['starts']

    att_adj = 1 + 0.08 * (3 - avg_fdr[e['team']])
    xgc = team_xgc90[e['team']] * (1 + 0.15 * (avg_fdr[e['team']] - 3))
    p_cs = math.exp(-xgc)

    if key in XMINS_OVERRIDE:
        xmins = XMINS_OVERRIDE[key]
    elif mins >= 400:
        xmins = mins / 38
    else:
        xmins = None  # new to PL / fringe -> price prior

    if xmins is not None and xmins > 0:
        frac = min(xmins / 90, 1.0)
        xg90 = float(e['expected_goals_per_90'])
        xa90 = float(e['expected_assists_per_90'])
        if key in XMINS_OVERRIDE and mins < 1500:
            # thin sample for promoted-role players: shrink rates toward 0
            shrink = max(mins / 1500, 0.3)
            xg90, xa90 = xg90 * shrink, xa90 * shrink
        appearance = 2 * frac
        goals = xg90 * frac * GOAL_VAL[pos] * att_adj
        assists = xa90 * frac * 3 * att_adj
        cs = p_cs * CS_VAL[pos] * frac if pos <= 3 else 0
        saves = (e['saves'] / 38) / 3 * frac if pos == 1 else 0
        dc_rate = e['defensive_contribution'] / 38 if mins else 0
        thresh = DEFCON_THRESH.get(pos)
        defcon = 2 * frac * min(1, max(0, (dc_rate / thresh - 0.4) / 0.6)) if thresh else 0
        bonus = e['bonus'] / 38 * frac
        xpts = appearance + goals + assists + cs + saves + defcon + bonus
    elif xmins == 0:
        xpts = 0.0
    else:
        xpts = 0.42 * price * 0.8  # price prior with regression haircut

    players.append({
        'id': e['id'], 'name': e['web_name'], 'team': e['team'], 'pos': pos,
        'price': price, 'sel': float(e['selected_by_percent']),
        'xpts': xpts * avail,
    })

# --- SCORES-END --- (dashboard.py exec's the file up to this marker)

print('=== TOP xPts/MATCH BY POSITION (prior-season Opta rates) ===')
for p in [1, 2, 3, 4]:
    for q in sorted([q for q in players if q['pos'] == p], key=lambda q: -q['xpts'])[:10]:
        print(f"{pos_name[p]} {q['name']:20} {teams[q['team']]:4} £{q['price']:4.1f} xPts={q['xpts']:.2f} sel={q['sel']:.1f}%")
    print()

# LP: maximize XI xPts + captain double + light bench weight
prob = pulp.LpProblem('fpl', pulp.LpMaximize)
x = {p['id']: pulp.LpVariable(f"x{p['id']}", cat='Binary') for p in players}
y = {p['id']: pulp.LpVariable(f"y{p['id']}", cat='Binary') for p in players}
c = {p['id']: pulp.LpVariable(f"c{p['id']}", cat='Binary') for p in players}
prob += pulp.lpSum(p['xpts'] * y[p['id']] for p in players) \
      + pulp.lpSum(p['xpts'] * c[p['id']] for p in players) \
      + 0.08 * pulp.lpSum(p['xpts'] * (x[p['id']] - y[p['id']]) for p in players)
prob += pulp.lpSum(p['price'] * x[p['id']] for p in players) <= 100.0
for pos, n in [(1, 2), (2, 5), (3, 5), (4, 3)]:
    prob += pulp.lpSum(x[p['id']] for p in players if p['pos'] == pos) == n
for t in teams:
    prob += pulp.lpSum(x[p['id']] for p in players if p['team'] == t) <= 3
prob += pulp.lpSum(y.values()) == 11
prob += pulp.lpSum(c.values()) == 1
for p in players:
    prob += y[p['id']] <= x[p['id']]
    prob += c[p['id']] <= y[p['id']]
prob += pulp.lpSum(y[p['id']] for p in players if p['pos'] == 1) == 1
prob += pulp.lpSum(y[p['id']] for p in players if p['pos'] == 2) >= 3
prob += pulp.lpSum(y[p['id']] for p in players if p['pos'] == 4) >= 1
prob.solve(pulp.PULP_CBC_CMD(msg=0))

V4 = {'Kinsky', 'Verbruggen', 'Guéhi', 'Mosquera', 'Maguire', 'Davis',
      'van Ewijk', 'B.Fernandes', 'Szoboszlai', 'Mbeumo', 'E.Le Fée',
      'Hughes', 'Haaland', 'João Pedro', 'Brobbey'}
squad = [p for p in players if x[p['id']].value() == 1]
print(f"=== MODEL-OPTIMAL SQUAD (£{sum(p['price'] for p in squad):.1f}m) vs v4 ===")
for pos in [1, 2, 3, 4]:
    for p in sorted([q for q in squad if q['pos'] == pos], key=lambda q: -q['xpts']):
        xi = 'XI ' if y[p['id']].value() == 1 else 'bch'
        cap = ' (C)' if c[p['id']].value() == 1 else ''
        mark = ' *IN V4*' if p['name'] in V4 else ''
        print(f"{xi} {pos_name[pos]} {p['name']:20} {teams[p['team']]:4} £{p['price']:4.1f} xPts={p['xpts']:.2f}{cap}{mark}")
model_names = {p['name'] for p in squad}
print('\nv4 players the model would NOT pick:', sorted(V4 - model_names))
