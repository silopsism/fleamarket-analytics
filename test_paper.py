import os, sys, json, copy
os.chdir(r'C:\Code\fpl'); sys.path.insert(0, r'C:\Code\fpl')
import paper

fails = []
def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} {label}: got {got} want {want}")
    if not ok: fails.append(label)

print('sell_price (tenths):')
check('rise 0.4 -> half, rounded down', paper.sell_price(65, 69), 67)
check('rise 0.5 -> half, rounded down', paper.sell_price(65, 70), 67)
check('rise 0.2', paper.sell_price(65, 67), 66)
check('rise 0.1 -> no profit yet', paper.sell_price(65, 66), 65)
check('unchanged', paper.sell_price(65, 65), 65)
check('fall takes the full hit', paper.sell_price(65, 62), 62)

# 1=GK 2=DEF 3=MID 4=FWD
POS = {}
def mk(ids, pos):
    for i in ids: POS[i] = pos
mk([1], 1); mk([2], 1)                      # keepers
mk([3,4,5,6], 2)                            # defenders
mk([7,8,9,10], 3)                           # midfielders
mk([11,12], 4)                              # forwards
XI    = [1, 3,4,5, 7,8,9,10, 11]            # 1-3-4-1 = 9, pad below
XI    = [1, 3,4,5,6, 7,8,9,10, 11,12]       # 1 GK, 4 DEF, 4 MID, 2 FWD = 11
BENCH = [2, 6, 10, 12]                      # keeper first, then outfield
BENCH = [2, 13, 14, 15]
mk([13], 2); mk([14], 3); mk([15], 4)

print('\napply_autosubs:')
allplay = {i: 90 for i in XI + BENCH}
fx, subs = paper.apply_autosubs(XI, BENCH, POS, allplay)
check('nobody blanks -> no subs', (sorted(fx), subs), (sorted(XI), []))

m = dict(allplay); m[11] = 0                # a forward blanks
fx, subs = paper.apply_autosubs(XI, BENCH, POS, m)
check('fwd blanks -> first eligible bench in', subs, [(11, 13)])

m = dict(allplay); m[1] = 0                 # keeper blanks
fx, subs = paper.apply_autosubs(XI, BENCH, POS, m)
check('keeper blanks -> bench keeper only', subs, [(1, 2)])

m = dict(allplay); m[1] = 0; m[2] = 0       # both keepers blank
fx, subs = paper.apply_autosubs(XI, BENCH, POS, m)
check('no playing keeper -> no sub', subs, [])

m = dict(allplay); m[3] = m[4] = 0          # two defenders blank, min DEF is 3
fx, subs = paper.apply_autosubs(XI, BENCH, POS, m)
check('formation floor respected', len(subs), 2)
counts = {}
for i in fx: counts[POS[i]] = counts.get(POS[i], 0) + 1
check('XI still legal', all(paper.XI_MIN[p] <= counts.get(p, 0) <= paper.XI_MAX[p]
                            for p in paper.XI_MIN), True)
check('XI still 11', len(fx), 11)

m = dict(allplay)
for i in BENCH: m[i] = 0                    # bench all blank
m[11] = 0
fx, subs = paper.apply_autosubs(XI, BENCH, POS, m)
check('bench all blank -> no subs', subs, [])

print('\nscore() end to end on synthetic live data:')
TMP = os.path.join('data', '_test_entry.json')
st = {'squad': [{'id': i, 'name': f'p{i}', 'club': 'XXX', 'pos': POS[i], 'buy': 50}
                for i in XI + BENCH],
      'xi': XI, 'bench': BENCH, 'cap': 8, 'vice': 9, 'bank': 0, 'ft': 1,
      'locked_gw': 1, 'start_gw': 1,
      'history': [{'gw': 1, 'xi': XI, 'bench': BENCH, 'cap': 8, 'vice': 9,
                   'transfers': {'in': [], 'out': [], 'in_ids': [], 'out_ids': [],
                                 'hits': 1},
                   'projected': 50.0, 'points': None, 'value': 1000, 'bank': 0}]}
paper.save(copy.deepcopy(st), TMP)
live = {i: {'minutes': 90, 'total_points': 2} for i in XI + BENCH}
live[8] = {'minutes': 90, 'total_points': 10}          # captain hauls
_, e = paper.score(1, path=TMP, live=live)
# XI: 10 players x2 + captain 10, doubled = 20, minus a 4-point hit
check('captain doubled, hit deducted', e['points'], 10 * 2 + 10 + 10 - 4)
check('captain used', e['captain_used'], 8)

paper.save(copy.deepcopy(st), TMP)
live2 = {i: {'minutes': 90, 'total_points': 2} for i in XI + BENCH}
live2[8] = {'minutes': 0, 'total_points': 0}           # captain blanks
live2[9] = {'minutes': 90, 'total_points': 7}          # vice plays
_, e2 = paper.score(1, path=TMP, live=live2)
check('armband falls to the vice', e2['captain_used'], 9)
# XI loses the captain (0 mins, subbed for bench mid 14 on 2), so 10x2 + 2 + vice 7 doubled
check('vice doubled after captain blank', e2['points'],
      (9 * 2 + 7 + 2) + 7 - 4)
os.remove(TMP)
print('\nFAILURES:', fails or 'none')
sys.exit(1 if fails else 0)
