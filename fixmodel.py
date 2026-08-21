"""Our own fixture-strength model — a continuous replacement for FPL's 1-5 rating.

A fixture is not one number. The same match can be good for attacking returns
and bad for defensive ones: an opponent may leak goals AND still carry a threat.
So each side's expected goals come from a multiplicative Dixon-Coles-style form
with SEPARATE exponents for the two directions:

    gf(home) = LEVEL * attack_home^k_att * concede_away^k_def * HOME
    gf(away) = LEVEL * attack_away^k_att * concede_home^k_def / HOME

k_att is how much a team's own attacking strength moves the line; k_def is how
much the opponent's leakiness does. Those, the home factor and the overall level
are all CALIBRATED against real bookmaker prices for whichever fixtures are
quoted, so the derived numbers inherit the market's spread and its level instead
of guessing at either.

Every fixture is then published in BOTH directions — an attack factor (af:
expected goals for, relative to that team's own season average) and a concession
factor (df, with the raw expected goals against and the clean-sheet probability
alongside) — so nothing downstream has to collapse the two back into a single
difficulty score.

Bookmaker odds still win for any fixture they cover; this fills in the rest.
"""
import math
import statistics

BASE = 1.45          # league-average goals per team per game
K_LO, K_HI = 0.30, 2.40
H_LO, H_HI = 1.00, 1.30
LEVEL_LO, LEVEL_HI = 0.70, 1.40
# Mild ridge on the gap between the two exponents. With only a handful of quoted
# fixtures the two directions are partly collinear, so they are allowed to
# separate only when the market really insists.
SPLIT_PENALTY = 0.15
# How far the exponents may be inflated to match the market's spread (below).
DISPERSION_CAP = 1.80


def _strengths(team_att, team_xgc, sent, med_att, med_xgc):
    """Per-team (attack, concede) ratios, tilted by season expectation."""
    att, con = {}, {}
    for t in team_att:
        s = sent.get(t, 1.0)
        att[t] = (team_att[t] * s) / med_att if med_att else 1.0
        con[t] = (team_xgc.get(t, med_xgc) / s) / med_xgc if med_xgc else 1.0
    return att, con


def predict(att, con, home, away, k_att, k_def, home_adv, base=BASE):
    """base should be the MEDIAN team's expected goals, so that an average
    attack against an average defence at a neutral venue returns the median."""
    gf_h = base * (att[home] ** k_att) * (con[away] ** k_def) * home_adv
    gf_a = base * (att[away] ** k_att) * (con[home] ** k_def) / home_adv
    return max(gf_h, 0.15), max(gf_a, 0.15)


def _loss(obs, base, k_a, k_d, h, lam):
    """Penalised squared error, with the overall level solved in closed form.

    For fixed exponents the best multiplicative level is sum(pm)/sum(p*p), so we
    never have to grid over it — and the market ends up setting our goal level
    instead of a hand-picked league average.
    """
    num = den = mm = 0.0
    for la_h, lc_a, la_a, lc_h, mh, ma in obs:
        ph = base * math.exp(k_a * la_h + k_d * lc_a) * h
        pa = base * math.exp(k_a * la_a + k_d * lc_h) / h
        num += ph * mh + pa * ma
        den += ph * ph + pa * pa
        mm += mh * mh + ma * ma
    if den <= 0:
        return float('inf'), 1.0, float('inf')
    s = min(max(num / den, LEVEL_LO), LEVEL_HI)
    sse = mm - 2 * s * num + s * s * den
    return sse + lam * (k_a - k_d) ** 2, s, sse


def _span(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [round(lo + step * i, 4) for i in range(n + 1)]


def _around(x, halfwidth, step, lo=None, hi=None):
    vals = _span(x - halfwidth, x + halfwidth, step)
    if lo is not None:
        vals = [v for v in vals if v >= lo]
    if hi is not None:
        vals = [v for v in vals if v <= hi]
    return vals or [x]


def _search(obs, base, ks_a, ks_d, hs, lam):
    best = None
    for k_a in ks_a:
        for k_d in ks_d:
            for h in hs:
                loss, s, sse = _loss(obs, base, k_a, k_d, h, lam)
                if best is None or loss < best[0]:
                    best = (loss, k_a, k_d, h, s, sse)
    return best


def _dispersion(obs, base, k_a, k_d, h, s):
    """sd(our expected goals) / sd(the market's), on the same fixtures."""
    mk, pr = [], []
    for la_h, lc_a, la_a, lc_h, mh, ma in obs:
        pr.append(s * base * math.exp(k_a * la_h + k_d * lc_a) * h)
        pr.append(s * base * math.exp(k_a * la_a + k_d * lc_h) / h)
        mk += [mh, ma]
    sd_m = statistics.pstdev(mk)
    return (statistics.pstdev(pr) / sd_m) if sd_m else 1.0


DEFAULTS = {'k_att': 1.0, 'k_def': 1.0, 'home_adv': 1.15, 'level': 1.0,
            'rmse': None, 'priced': 0, 'gamma': 1.0, 'dispersion': None,
            'rmse_ls': None}


def calibrate(att, con, priced, base=BASE):
    """Fit (k_att, k_def, home_adv, level) to quoted fixtures.

    priced: [(home, away, market_gf_home, market_gf_away)]. Coarse grid then a
    local refinement — cheaper and finer than one flat sweep.
    """
    obs = []
    for home, away, mh, ma in priced:
        if home not in att or away not in att or min(mh, ma) <= 0:
            continue
        obs.append((math.log(att[home]), math.log(con[away]),
                    math.log(att[away]), math.log(con[home]), mh, ma))
    if len(obs) < 3:
        return dict(DEFAULTS, priced=len(obs))

    lam = SPLIT_PENALTY * len(obs)
    ks, hs = _span(K_LO, K_HI, 0.10), _span(H_LO, H_HI, 0.04)
    coarse = _search(obs, base, ks, ks, hs, lam)
    fine = _search(obs, base,
                   _around(coarse[1], 0.10, 0.02, K_LO, K_HI),
                   _around(coarse[2], 0.10, 0.02, K_LO, K_HI),
                   _around(coarse[3], 0.04, 0.01, H_LO, H_HI), lam)
    loss, k_a, k_d, h, s, sse = min(coarse, fine, key=lambda b: b[0])
    rmse_ls = (sse / (2 * len(obs))) ** 0.5
    disp_ls = _dispersion(obs, base, k_a, k_d, h, s)

    # Least squares gives the best guess for a single fixture, but a shrunken
    # one: the fitted spread comes out narrower than the market's, and that
    # compression is precisely what makes week-to-week projections look flatter
    # than they should. So inflate both exponents by a common factor until the
    # spread matches, re-solving the level each time so the mean stays right.
    # Single-fixture rmse gets worse; the distribution of fixture
    # attractiveness — which is what a planner actually reads — gets honest.
    gamma, best_gap = 1.0, abs(disp_ls - 1.0)
    for g in _span(1.0, DISPERSION_CAP, 0.02):
        ka, kd = min(k_a * g, K_HI), min(k_d * g, K_HI)
        _, sg, _ = _loss(obs, base, ka, kd, h, 0.0)
        gap = abs(_dispersion(obs, base, ka, kd, h, sg) - 1.0)
        if gap < best_gap:
            gamma, best_gap = g, gap
    k_a, k_d = min(k_a * gamma, K_HI), min(k_d * gamma, K_HI)
    _, s, sse = _loss(obs, base, k_a, k_d, h, 0.0)

    return {'k_att': round(k_a, 3), 'k_def': round(k_d, 3), 'home_adv': h,
            'level': round(s, 4), 'gamma': round(gamma, 2),
            'rmse': round((sse / (2 * len(obs))) ** 0.5, 3),
            'rmse_ls': round(rmse_ls, 3),
            'dispersion': round(_dispersion(obs, base, k_a, k_d, h, s), 3),
            'dispersion_ls': round(disp_ls, 3), 'priced': len(obs)}


def build(fixtures, teams, team_att, team_xgc, sent, med_att, med_xgc,
          odds_teams, events, med_xg_base=None):
    """Expected goals for every fixture, in both directions.

    Returns (per_team, meta) where per_team[short][event] = {'gf','ga','af','df',
    'cs','src','home','opp'}: gf/ga are expected goals for and against, af/df
    express each of those relative to that team's own season average (so af 1.15
    means 15% better for attackers than their normal fixture), and cs is the
    clean-sheet probability.
    """
    med_xgc = med_xgc or 1.4
    att, con = _strengths(team_att, team_xgc, sent, med_att, med_xgc)

    priced = []
    for f in fixtures:
        if not f['event'] or f['event'] not in events:
            continue
        h, a = teams[f['team_h']], teams[f['team_a']]
        oh = (odds_teams.get(h) or {}).get(str(f['event']))
        if oh and oh.get('home'):
            priced.append((h, a, oh['gf'], oh['ga']))
    base = med_xg_base or BASE
    cal = calibrate(att, con, priced, base)
    # the market's own goal level, rather than our squad-sum proxy for it
    base_eff = base * cal['level']

    per_team, n_odds, n_model = {}, 0, 0
    for f in fixtures:
        if not f['event']:
            continue
        h, a = teams[f['team_h']], teams[f['team_a']]
        ev = str(f['event'])
        oh = (odds_teams.get(h) or {}).get(ev)
        if oh:
            gf_h, gf_a, src = oh['gf'], oh['ga'], 'odds'
            n_odds += 1
        else:
            gf_h, gf_a = predict(att, con, h, a, cal['k_att'], cal['k_def'],
                                 cal['home_adv'], base_eff)
            src = 'model'
            n_model += 1
        per_team.setdefault(h, {})[ev] = {'gf': round(gf_h, 2), 'ga': round(gf_a, 2),
                                          'src': src, 'home': 1, 'opp': a}
        per_team.setdefault(a, {})[ev] = {'gf': round(gf_a, 2), 'ga': round(gf_h, 2),
                                          'src': src, 'home': 0, 'opp': h}

    # each team's own season averages: the denominators that turn an
    # average-fixture rate into a this-fixture rate, one per direction
    avg_gf, avg_ga = {}, {}
    for c, evs in per_team.items():
        gfs = [v['gf'] for v in evs.values()]
        gas = [v['ga'] for v in evs.values()]
        avg_gf[c] = round(sum(gfs) / len(gfs), 3) if gfs else base_eff
        avg_ga[c] = round(sum(gas) / len(gas), 3) if gas else med_xgc
    for c, evs in per_team.items():
        for v in evs.values():
            v['af'] = round(v['gf'] / (avg_gf[c] or 1), 3)
            v['df'] = round(v['ga'] / (avg_ga[c] or 1), 3)
            v['cs'] = round(math.exp(-max(v['ga'], 0.15)), 3)

    meta = {k: cal[k] for k in cal}
    meta.update({'base': round(base_eff, 3), 'avg_gf': avg_gf, 'avg_ga': avg_ga,
                 'odds_fixtures': n_odds, 'model_fixtures': n_model})
    return per_team, meta
