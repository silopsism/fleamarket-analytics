"""Initial FPL analysis: prices, opening fixtures, fixture difficulty."""
import json
from collections import defaultdict

d = json.load(open('bootstrap.json', encoding='utf-8'))
fx = json.load(open('fixtures.json', encoding='utf-8'))

teams = {t['id']: t['short_name'] for t in d['teams']}
pos = {et['id']: et['singular_name_short'] for et in d['element_types']}

# Fixture difficulty for first 6 GWs per team
runs = defaultdict(list)
for f in fx:
    if f['event'] and f['event'] <= 6:
        runs[f['team_h']].append((f['event'], teams[f['team_a']], f['team_h_difficulty'], 'H'))
        runs[f['team_a']].append((f['event'], teams[f['team_h']], f['team_a_difficulty'], 'A'))

print('=== FIXTURE RUNS GW1-6 (sorted easiest first) ===')
avg = []
for tid, games in runs.items():
    games.sort()
    total = sum(g[2] for g in games)
    avg.append((total / len(games), teams[tid], games))
avg.sort()
for a, name, games in avg:
    s = ' '.join(f"{opp}({'h' if ha=='H' else 'a'}){diff}" for _, opp, diff, ha in games)
    print(f"{name:4} avgFDR={a:.2f}  {s}")

print()
print('=== TOP PLAYERS BY POSITION (price desc) ===')
els = d['elements']
for p in [1, 2, 3, 4]:
    print(f"--- {pos[p]} ---")
    ps = [e for e in els if e['element_type'] == p]
    ps.sort(key=lambda e: -e['now_cost'])
    for e in ps[:20]:
        flag = e['status'] if e['status'] != 'a' else ' '
        print(f"  {e['web_name']:22} {teams[e['team']]:4} £{e['now_cost']/10:.1f} sel={e['selected_by_percent']:>5}% {flag} {e['news'][:50]}")
