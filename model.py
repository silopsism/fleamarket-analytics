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

from minutes import expected_minutes

HORIZON = 4          # gameweeks for fixture adjustment
GOAL_VAL = {1: 10, 2: 6, 3: 5, 4: 4}
CS_VAL = {1: 4, 2: 4, 3: 1, 4: 0}
DEFCON_THRESH = {2: 10, 3: 12, 4: 12}

d = json.load(open('bootstrap.json', encoding='utf-8'))
fx = json.load(open('fixtures.json', encoding='utf-8'))
teams = {t['id']: t['short_name'] for t in d['teams']}
pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

# fixture difficulty per team: horizon average + per-event lists (handles
# doubles as two entries and blanks as missing)
fdr = defaultdict(list)
next_event = min(e['id'] for e in d['events'] if not e['finished'])
HORIZON_EVENTS = list(range(next_event, next_event + HORIZON))
ev_fdr = defaultdict(lambda: defaultdict(list))
for f in fx:
    if f['event'] and f['event'] in HORIZON_EVENTS:
        fdr[f['team_h']].append(f['team_h_difficulty'])
        fdr[f['team_a']].append(f['team_a_difficulty'])
        ev_fdr[f['team_h']][f['event']].append(f['team_h_difficulty'])
        ev_fdr[f['team_a']][f['event']].append(f['team_a_difficulty'])
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

XMINS = expected_minutes(d)

# team attack strength: minutes-weighted xGI/90 of the CURRENT squad (>=900
# prior-season minutes), for transfer-context adjustment of movers' rates
ta = defaultdict(lambda: [0.0, 0.0])
for e in d['elements']:
    if e['minutes'] >= 900 and e['element_type'] >= 3:
        ta[e['team']][0] += float(e['expected_goal_involvements_per_90']) * e['minutes']
        ta[e['team']][1] += e['minutes']
team_att = {t: (v[0] / v[1] if v[1] else 0) for t, v in ta.items()}
med_att = sorted(x for x in team_att.values() if x)[len(team_att) // 2]
for t in teams:
    if not team_att.get(t):
        team_att[t] = med_att * 0.7   # promoted sides: weak attack prior
team_att['RELEGATED'] = med_att * 0.85

import os
CTX = {}
if os.path.exists('context_adjustments.json'):
    CTX = {k: v for k, v in json.load(open('context_adjustments.json', encoding='utf-8')).items()
           if not k.startswith('_')}
short2id = {v: k for k, v in teams.items()}

# season-expectation sentiment: predicted vs last-season league points per club
# (betting-market/Elo based), sqrt-dampened, applied to attack rates and
# inversely to team xGC. Promoted clubs (no 'last') stay at 1.0.
SENT = {t: 1.0 for t in teams}
if os.path.exists('team_sentiment.json'):
    for short, v in json.load(open('team_sentiment.json', encoding='utf-8')).items():
        if short.startswith('_') or short not in short2id or 'last' not in v:
            continue
        SENT[short2id[short]] = min(max((v['pred'] / v['last']) ** 0.5, 0.87), 1.15)

players = []
for e in d['elements']:
    price = e['now_cost'] / 10
    pos = e['element_type']
    mins, starts = e['minutes'], e['starts']

    sent = SENT[e['team']]
    base_xgc = team_xgc90[e['team']] / sent   # improving team -> concedes less
    att_adj = 1 + 0.10 * (3 - avg_fdr[e['team']])
    xgc = base_xgc * (1 + 0.18 * (avg_fdr[e['team']] - 3))
    p_cs = math.exp(-xgc)
    # per-fixture adjustments for each horizon event (stronger single-game swing;
    # ±16%/FDR-pt attack, ±26% xGC — still flatter than odds-implied spreads,
    # pending the Phase 3 bookmaker-odds fixture model)
    ev_adjs = {ev: [(1 + 0.16 * (3 - fd), base_xgc * (1 + 0.26 * (fd - 3)))
                    for fd in ev_fdr[e['team']].get(ev, [])]
               for ev in HORIZON_EVENTS}

    xmins = XMINS[e['id']]['xmins']   # availability already applied inside
    xmins_src = XMINS[e['id']]['src']
    if mins < 400 and xmins > 0:
        xmins_mode = 'prior'          # no PL rate data -> price prior
    elif xmins > 0:
        xmins_mode = 'rates'
    else:
        xmins_mode = 'out'

    if xmins_mode == 'rates':
        frac = min(xmins / 90, 1.0)
        # finishing-skill shrinkage: 75% chance quality (xG), 25% actual output.
        # Single-season overperformance is mostly noise, but not entirely —
        # persistent finishers keep a quarter of their edge.
        g90 = e['goals_scored'] / (mins / 90)
        a90 = e['assists'] / (mins / 90)
        xg90 = 0.75 * float(e['expected_goals_per_90']) + 0.25 * g90
        xa90 = 0.75 * float(e['expected_assists_per_90']) + 0.25 * a90
        okey = f"{e['web_name']}|{teams[e['team']]}"
        if okey in CTX:
            # transfer-context factor: rates were earned at the origin club
            frm = CTX[okey]['from']
            origin = team_att.get(short2id.get(frm), team_att.get(frm, med_att))
            factor = (team_att[e['team']] / origin) ** 0.5 if origin else 1.0
            factor = min(max(factor, 0.85), 1.15)
            xg90, xa90 = xg90 * factor, xa90 * factor
        if mins < 1500 and xmins > mins / 38 * 1.5 and not XMINS[e['id']]['trust']:
            # promoted role on a thin sample: shrink attack rates toward 0
            # (trust_rates overrides skip this - e.g. injury-shortened stars)
            shrink = max(mins / 1500, 0.3)
            xg90, xa90 = xg90 * shrink, xa90 * shrink
        xg90, xa90 = xg90 * sent, xa90 * sent   # season-expectation sentiment
        appearance = 2 * frac
        # per-90 rates scaled by expected minutes (identical to season/38 for
        # regular starters, but respects xmins overrides for role changers)
        saves = (e['saves'] / (mins / 90) if mins else 0) / 3 * frac if pos == 1 else 0
        dc_mean = e['defensive_contribution'] / (mins / 90) * frac if mins else 0
        thresh = DEFCON_THRESH.get(pos)
        # P(hitting the defcon threshold) via Poisson tail, not certainty
        defcon = 2 * (1 - sum(math.exp(-dc_mean) * dc_mean ** k / math.factorial(k)
                              for k in range(thresh))) if thresh and dc_mean > 0 else 0
        # per-played-90 basis: bonus/38 would double-discount players who
        # missed games (availability is already priced into frac)
        bonus = e['bonus'] / (mins / 90) * frac if mins else 0
        # designated #1 penalty taker: half-credit bonus (incumbents' rates
        # already contain some of their past pens; new takers gain most)
        pen = 0.04 * GOAL_VAL[pos] * frac if e['penalties_order'] == 1 else 0
        yc_pen = e['yellow_cards'] / (mins / 90) * frac if mins else 0

        def _pts(att, xgc_v):
            goals = xg90 * frac * GOAL_VAL[pos] * att
            assists = xa90 * frac * 3 * att
            cs = math.exp(-xgc_v) * CS_VAL[pos] * frac if pos <= 3 else 0
            gc = (xgc_v / 2) * frac if pos <= 2 else 0
            return (appearance + goals + assists + cs + saves + defcon
                    + bonus + pen - gc - yc_pen)

        xpts = _pts(att_adj, xgc)
        gws = [sum(_pts(a, g) for a, g in ev_adjs[ev]) for ev in HORIZON_EVENTS]
    elif xmins_mode == 'out':
        xpts = 0.0
        gws = [0.0] * HORIZON
    else:
        # no PL rate data: build from what we DO know — appearance points from
        # expected minutes, team-level clean sheets (fixture-adjusted), a modest
        # defcon prior for DEF/MID — plus a price-based guess only for attack
        frac = min(xmins / 90, 1.0)
        appearance = 2 * frac
        dc_prior = 0.4 * frac if pos in (2, 3) else 0
        pen = 0.04 * GOAL_VAL[pos] * frac if e['penalties_order'] == 1 else 0

        def _prior(att, xgc_v):
            cs = math.exp(-xgc_v) * CS_VAL[pos] * frac if pos <= 3 else 0
            return appearance + cs + 0.10 * price * frac * att * sent + dc_prior + pen

        xpts = _prior(att_adj, xgc)
        gws = [sum(_prior(a, g) for a, g in ev_adjs[ev]) for ev in HORIZON_EVENTS]

    players.append({
        'id': e['id'], 'name': e['web_name'], 'team': e['team'], 'pos': pos,
        'price': price, 'sel': float(e['selected_by_percent']),
        'xpts': xpts, 'xnext': gws[0], 'gws': [round(g, 2) for g in gws],
        'tot4': round(sum(gws), 2), 'xmins': round(xmins), 'src': xmins_src,
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
