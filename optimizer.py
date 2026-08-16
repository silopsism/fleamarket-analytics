"""GW1 squad optimizer: maximize blended projection under FPL rules.

Score = 0.55 * ep_next (FPL's own projection)
      + 0.30 * ownership consensus (sqrt-dampened)
      + 0.15 * fixture ease GW1-6
Injured/doubtful players are excluded or penalized.
"""
import json
import math
from collections import defaultdict
import pulp

d = json.load(open('bootstrap.json', encoding='utf-8'))
fx = json.load(open('fixtures.json', encoding='utf-8'))

teams = {t['id']: t['short_name'] for t in d['teams']}
pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

# team fixture ease GW1-6: 5 - avg difficulty, normalized 0..1
fdr = defaultdict(list)
for f in fx:
    if f['event'] and f['event'] <= 6:
        fdr[f['team_h']].append(f['team_h_difficulty'])
        fdr[f['team_a']].append(f['team_a_difficulty'])
ease = {t: (5 - sum(v) / len(v)) / 3 for t, v in fdr.items()}

players = []
for e in d['elements']:
    if e['status'] in ('i', 'u', 'n', 's'):  # injured/unavailable/etc
        continue
    ep = float(e['ep_next'] or 0)
    if ep <= 0:
        continue
    sel = float(e['selected_by_percent'])
    chance = e['chance_of_playing_next_round']
    avail = (chance / 100) if chance is not None else 1.0
    score = (0.55 * (ep / 4.0) + 0.30 * (math.sqrt(sel) / math.sqrt(75)) +
             0.15 * ease[e['team']]) * avail
    players.append({
        'id': e['id'], 'name': e['web_name'], 'team': e['team'],
        'pos': e['element_type'], 'price': e['now_cost'] / 10,
        'sel': sel, 'ep': ep, 'score': score,
    })

prob = pulp.LpProblem('fpl', pulp.LpMaximize)
x = {p['id']: pulp.LpVariable(f"x{p['id']}", cat='Binary') for p in players}  # squad
y = {p['id']: pulp.LpVariable(f"y{p['id']}", cat='Binary') for p in players}  # XI
c = {p['id']: pulp.LpVariable(f"c{p['id']}", cat='Binary') for p in players}  # captain

prob += pulp.lpSum(p['score'] * y[p['id']] for p in players) \
      + pulp.lpSum(p['score'] * c[p['id']] for p in players) \
      + 0.08 * pulp.lpSum(p['score'] * (x[p['id']] - y[p['id']]) for p in players)

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
print('status:', pulp.LpStatus[prob.status])

squad = [p for p in players if x[p['id']].value() == 1]
cost = sum(p['price'] for p in squad)
print(f'total cost: £{cost:.1f}m  |  bank: £{100 - cost:.1f}m')
for pos in [1, 2, 3, 4]:
    for p in sorted([q for q in squad if q['pos'] == pos], key=lambda q: -q['score']):
        xi = 'XI ' if y[p['id']].value() == 1 else 'bch'
        cap = ' (C)' if c[p['id']].value() == 1 else ''
        print(f"{xi} {pos_name[pos]} {p['name']:20} {teams[p['team']]:4} £{p['price']:4.1f} "
              f"sel={p['sel']:5.1f}% ep={p['ep']:.1f} score={p['score']:.3f}{cap}")
