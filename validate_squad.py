"""Validate a proposed 15-man squad: cost, quotas, club limits."""
import json
import sys
from collections import Counter

d = json.load(open('bootstrap.json', encoding='utf-8'))
teams = {t['id']: t['short_name'] for t in d['teams']}
pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

SQUAD = [
    ('Kinsky', 'TOT'), ('Verbruggen', 'BHA'),
    ('Guéhi', 'MCI'), ('Mosquera', 'ARS'), ('Maguire', 'MUN'),
    ('Davis', 'IPS'), ('van Ewijk', 'COV'),
    ('B.Fernandes', 'MUN'), ('Szoboszlai', 'LIV'), ('Mbeumo', 'MUN'),
    ('E.Le Fée', 'SUN'), ('Hughes', 'CRY'),
    ('Haaland', 'MCI'), ('João Pedro', 'CHE'), ('Calvert-Lewin', 'LEE'),
]

picked = []
for name, club in SQUAD:
    hits = [e for e in d['elements']
            if e['web_name'] == name and teams[e['team']] == club]
    if len(hits) != 1:
        sys.exit(f'lookup failed: {name} {club} -> {len(hits)} hits')
    picked.append(hits[0])

cost = sum(e['now_cost'] for e in picked) / 10
quota = Counter(e['element_type'] for e in picked)
clubs = Counter(teams[e['team']] for e in picked)

print(f'cost £{cost:.1f}m | bank £{100 - cost:.1f}m')
print('quota ok:', quota[1] == 2 and quota[2] == 5 and quota[3] == 5 and quota[4] == 3)
print('club limit ok:', all(v <= 3 for v in clubs.values()), dict(clubs))
for e in picked:
    flag = e['status'] if e['status'] != 'a' else ''
    print(f"{pos_name[e['element_type']]} {e['web_name']:15} {teams[e['team']]:4} "
          f"£{e['now_cost']/10:4.1f} sel={e['selected_by_percent']:>5}% {flag}{e['news'][:40]}")
