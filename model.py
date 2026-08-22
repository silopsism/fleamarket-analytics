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

# bootstrap-static holds only the CURRENT season, and FPL zeroes every stat at
# the rollover - which broke this model outright at 2026/27's first deadline.
# history.json carries the prior season, keyed by the cross-season `code`, and
# merge() blends it with whatever the new season has accumulated so far.
HIST_META, PRIORS = {}, {}
try:
    import history as _history
    HIST_META = _history.merge(d, fixtures=fx)
    # what players of this price and position actually did last season, for
    # anyone with no Premier League record of their own
    PRIORS = _history.priors()
except Exception as _he:  # noqa: BLE001 - a missing snapshot must not be fatal
    HIST_META = {'error': str(_he)[:80]}
teams = {t['id']: t['short_name'] for t in d['teams']}
pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

# fixture difficulty per team: horizon average + per-event lists (handles
# doubles as two entries and blanks as missing)
fdr = defaultdict(list)
next_event = min(e['id'] for e in d['events'] if not e['finished'])
HORIZON_EVENTS = list(range(next_event, next_event + HORIZON))
ev_fdr = defaultdict(lambda: defaultdict(list))
ev_opp = defaultdict(lambda: defaultdict(list))
for f in fx:
    if f['event'] and f['event'] in HORIZON_EVENTS:
        fdr[f['team_h']].append(f['team_h_difficulty'])
        fdr[f['team_a']].append(f['team_a_difficulty'])
        ev_fdr[f['team_h']][f['event']].append(f['team_h_difficulty'])
        ev_fdr[f['team_a']][f['event']].append(f['team_a_difficulty'])
        ev_opp[f['team_h']][f['event']].append(f['team_a'])
        ev_opp[f['team_a']][f['event']].append(f['team_h'])
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
med_xgc90 = sorted(team_xgc90.values())[len(team_xgc90) // 2]

XMINS = expected_minutes(d)

# team attack strength: minutes-weighted xGI/90 of the CURRENT squad (>=900
# prior-season minutes), for transfer-context adjustment of movers' rates
ta = defaultdict(lambda: [0.0, 0.0])
for e in d['elements']:
    if e['minutes'] >= 900 and e['element_type'] >= 3:
        ta[e['team']][0] += float(e['expected_goal_involvements_per_90']) * e['minutes']
        ta[e['team']][1] += e['minutes']
team_att = {t: (v[0] / v[1] if v[1] else 0) for t, v in ta.items()}
_att_vals = sorted(x for x in team_att.values() if x)
# an empty list here means every stat is zero, i.e. history.json is missing at a
# season rollover. Fail loudly rather than with an IndexError six lines later.
if not _att_vals:
    raise SystemExit('no attacking data for any club - is history.json missing? '
                     'run: python history.py build bootstrap_old.json')
med_att = _att_vals[min(len(team_att) // 2, len(_att_vals) - 1)]
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

# bookmaker odds per fixture, if a cache exists (see odds.py)
ODDS = None
try:
    import odds as _odds_mod
    _oc = _odds_mod.load()
    if _oc and _oc.get('teams'):
        ODDS = _oc
except Exception:
    ODDS = None

# our own continuous fixture model, calibrated against whatever the bookmakers
# have quoted; it replaces FPL's 1-5 difficulty rating for unquoted fixtures
FIXMAP, FIXMETA = {}, {}
_PLACEHOLDER_SENT_ = True

# season-expectation sentiment: predicted vs last-season league points per club
# (betting-market/Elo based), sqrt-dampened, applied to attack rates and
# inversely to team xGC. Promoted clubs (no 'last') stay at 1.0.
SENT = {t: 1.0 for t in teams}
if os.path.exists('team_sentiment.json'):
    for short, v in json.load(open('team_sentiment.json', encoding='utf-8')).items():
        if short.startswith('_') or short not in short2id or 'last' not in v:
            continue
        SENT[short2id[short]] = min(max((v['pred'] / v['last']) ** 0.5, 0.87), 1.15)

# team attack for the FIXTURE model: total expected goals per match of the
# current squad. Far more discriminating than a per-player average (2.15 for
# City vs 0.69 for Fulham), but promoted clubs have no PL history at all, so
# they get a weak-but-real prior instead of ~0.
PROMOTED_XG_PRIOR = 1.05
_tot_xg = {}
for _e in d['elements']:
    _c = teams[_e['team']]
    _tot_xg[_c] = _tot_xg.get(_c, 0.0) + float(_e['expected_goals'])
TEAM_XG_PM = {c: v / 38 for c, v in _tot_xg.items()}
for _c, _v in list(TEAM_XG_PM.items()):
    if _v < 0.45:                      # no meaningful PL sample
        TEAM_XG_PM[_c] = PROMOTED_XG_PRIOR

try:
    import fixmodel
    _sent_short = {teams[t]: v for t, v in SENT.items()}
    _xgc_short = {teams[t]: v for t, v in team_xgc90.items()}
    _med_xgc = sorted(_xgc_short.values())[len(_xgc_short) // 2]
    _med_xg = sorted(TEAM_XG_PM.values())[len(TEAM_XG_PM) // 2]
    FIXMAP, FIXMETA = fixmodel.build(
        fx, teams, TEAM_XG_PM, _xgc_short, _sent_short, _med_xg, _med_xgc,
        (ODDS or {}).get('teams') or {}, set(HORIZON_EVENTS),
        med_xg_base=_med_xg)
except Exception as _fe:
    FIXMAP, FIXMETA = {}, {'error': str(_fe)[:80]}

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
    # per-fixture adjustments for each horizon event, and deliberately TWO of
    # them: a fixture is not one difficulty number. The attack side comes from
    # how leaky the opponent is, the defensive side from how dangerous they are,
    # and those routinely disagree — a promoted side may be easy to score past
    # and still carry enough threat to spoil a clean sheet.
    _fix_team = FIXMAP.get(teams[e['team']]) or {}
    ev_adjs = {}
    for ev in HORIZON_EVENTS:
        o = _fix_team.get(str(ev))
        if o:
            # af is already this fixture's expected goals relative to the team's
            # OWN season average, which is the right denominator: a player's
            # xG/90 is an average-fixture rate. ga stays absolute because clean
            # sheets and the concession penalty are levels, not ratios.
            ev_adjs[ev] = [(min(max(o['af'], 0.5), 1.7), max(o['ga'], 0.25))]
        else:
            # fixmodel unavailable: still split the two directions rather than
            # leaning on FPL's single rating, which conflates them
            adjs = []
            for _opp in ev_opp[e['team']].get(ev, []):
                leaky = (team_xgc90[_opp] / med_xgc90) ** 0.6      # good for us
                threat = (team_att[_opp] / med_att) ** 0.8         # bad for us
                adjs.append((min(max(leaky, 0.6), 1.6),
                             base_xgc * min(max(threat, 0.55), 1.7)))
            ev_adjs[ev] = adjs

    xmins = XMINS[e['id']]['xmins']   # availability already applied inside
    xmins_src = XMINS[e['id']]['src']
    if mins < 400 and xmins > 0:
        xmins_mode = 'prior'          # no PL rate data -> price prior
    elif xmins > 0:
        xmins_mode = 'rates'
    else:
        xmins_mode = 'out'

    # a player's minutes can climb across the horizon rather than sit flat (a new
    # signing bedding in, someone short of pre-season), so every component is
    # evaluated per gameweek at that week's minutes
    ramp = XMINS[e['id']].get('ramp')
    xmins_gw = [ramp[i] if ramp and i < len(ramp) else xmins for i in range(HORIZON)]

    if xmins_mode == 'rates':
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
        # per-90 rates; each is scaled by THAT gameweek's expected minutes below
        r_saves = (e['saves'] / (mins / 90) if mins else 0) if pos == 1 else 0
        r_dc = e['defensive_contribution'] / (mins / 90) if mins else 0
        # per-played-90 basis: bonus/38 would double-discount players who
        # missed games (availability is already priced into frac)
        r_bonus = e['bonus'] / (mins / 90) if mins else 0
        r_yc = e['yellow_cards'] / (mins / 90) if mins else 0
        thresh = DEFCON_THRESH.get(pos)

        def _pts(att, xgc_v, frac):
            goals = xg90 * frac * GOAL_VAL[pos] * att
            assists = xa90 * frac * 3 * att
            cs = math.exp(-xgc_v) * CS_VAL[pos] * frac if pos <= 3 else 0
            gc = (xgc_v / 2) * frac if pos <= 2 else 0
            # P(hitting the defcon threshold) via Poisson tail, not certainty.
            # Non-linear in minutes, so it is recomputed per gameweek rather
            # than scaled: a 45-minute cameo is far less than half as likely to
            # reach the threshold as a full 90.
            dc_mean = r_dc * frac
            defcon = 2 * (1 - sum(math.exp(-dc_mean) * dc_mean ** k / math.factorial(k)
                                  for k in range(thresh))) if thresh and dc_mean > 0 else 0
            # designated #1 penalty taker: half-credit bonus (incumbents' rates
            # already contain some of their past pens; new takers gain most)
            pen = 0.04 * GOAL_VAL[pos] * frac if e['penalties_order'] == 1 else 0
            return (2 * frac + goals + assists + cs + r_saves / 3 * frac + defcon
                    + r_bonus * frac + pen - gc - r_yc * frac)

        gws = [sum(_pts(a, g, min(mm / 90, 1.0)) for a, g in ev_adjs[ev])
               for ev, mm in zip(HORIZON_EVENTS, xmins_gw)]
        # headline xPts is the mean of the actual fixtures, so bookmaker odds
        # reach the value tables too (it used to use the FDR average only)
        xpts = sum(gws) / len(gws) if gws else _pts(att_adj, xgc, min(xmins / 90, 1.0))
    elif xmins_mode == 'out':
        xpts = 0.0
        gws = [0.0] * HORIZON
    else:
        # No PL record of his own, so stand in the median player of his price and
        # position from last season and score him the normal way. The old flat
        # "0.10 x price" was position-blind and about half the real rate for
        # attackers - which is how a 6.5m Arsenal winger ended up credited with
        # 0.13 points of attacking return.
        _pr = _history.prior_for(PRIORS, pos, price) if PRIORS else None
        # prior_mult is the one place a judgement about pre-season form can enter:
        # it says "better than the typical player at this price", which is what a
        # strong pre-season actually tells you, without inventing an xG90
        _pm = XMINS[e['id']].get('prior_mult') or 1.0
        p_xg = (_pr['xg90'] if _pr else 0.02 * price) * sent * _pm
        p_xa = (_pr['xa90'] if _pr else 0.02 * price) * sent * _pm
        p_dc = _pr['dc90'] if _pr else (4.0 if pos in (2, 3) else 0.0)
        p_bonus = _pr['bonus90'] if _pr else 0.0
        thresh = DEFCON_THRESH.get(pos)

        def _prior(att, xgc_v, frac):
            goals = p_xg * frac * GOAL_VAL[pos] * att
            assists = p_xa * frac * 3 * att
            cs = math.exp(-xgc_v) * CS_VAL[pos] * frac if pos <= 3 else 0
            gc = (xgc_v / 2) * frac if pos <= 2 else 0
            dcm = p_dc * frac
            defcon = 2 * (1 - sum(math.exp(-dcm) * dcm ** k / math.factorial(k)
                                  for k in range(thresh))) if thresh and dcm > 0 else 0
            pen = 0.04 * GOAL_VAL[pos] * frac if e['penalties_order'] == 1 else 0
            return (2 * frac + goals + assists + cs + defcon + p_bonus * frac
                    + pen - gc)

        gws = [sum(_prior(a, g, min(mm / 90, 1.0)) for a, g in ev_adjs[ev])
               for ev, mm in zip(HORIZON_EVENTS, xmins_gw)]
        xpts = sum(gws) / len(gws) if gws else _prior(att_adj, xgc, min(xmins / 90, 1.0))

    players.append({
        'id': e['id'], 'name': e['web_name'], 'team': e['team'], 'pos': pos,
        'price': price, 'sel': float(e['selected_by_percent']),
        'xpts': xpts, 'xnext': gws[0], 'gws': [round(g, 2) for g in gws],
        'tot4': round(sum(gws), 2), 'xmins': round(xmins), 'src': xmins_src,
        'xmins_gws': [round(m) for m in xmins_gw] if ramp else None,
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
