"""Our own fixture-strength model — a continuous replacement for FPL's 1-5 rating.

Expected goals for a fixture come from a multiplicative Dixon-Coles-style form:

    gf(home) = BASE * (attack_home / med)^k * (concede_away / med)^k * HOME
    gf(away) = BASE * (attack_away / med)^k * (concede_home / med)^k / HOME

Attack and concession strengths are the squad aggregates the player model already
builds, adjusted by season expectation. The exponent k and the home factor are
CALIBRATED against real bookmaker prices for whichever fixtures are quoted, so
the derived numbers inherit the market's spread instead of guessing at it.

Bookmaker odds still win for any fixture they cover; this fills in the rest.
"""
BASE = 1.45          # league-average goals per team per game
GRID_K = [round(0.4 + 0.05 * i, 2) for i in range(37)]        # 0.40 .. 2.20
GRID_HOME = [round(1.00 + 0.02 * i, 2) for i in range(16)]    # 1.00 .. 1.30


def _strengths(team_att, team_xgc, sent, med_att, med_xgc):
    """Per-team (attack, concede) ratios, tilted by season expectation."""
    att, con = {}, {}
    for t in team_att:
        s = sent.get(t, 1.0)
        att[t] = (team_att[t] * s) / med_att if med_att else 1.0
        con[t] = (team_xgc.get(t, med_xgc) / s) / med_xgc if med_xgc else 1.0
    return att, con


def predict(att, con, home, away, k, home_adv, base=BASE):
    """base should be the MEDIAN team's expected goals, so that an average
    attack against an average defence at a neutral venue returns the median."""
    gf_h = base * (att[home] ** k) * (con[away] ** k) * home_adv
    gf_a = base * (att[away] ** k) * (con[home] ** k) / home_adv
    return max(gf_h, 0.15), max(gf_a, 0.15)


def calibrate(att, con, priced, base=BASE):
    """Fit (k, home_adv) to quoted fixtures. priced: [(home, away, gf_h, gf_a)]."""
    if len(priced) < 3:
        return 1.0, 1.15, None
    best = None
    for k in GRID_K:
        for h in GRID_HOME:
            err = 0.0
            for home, away, mh, ma in priced:
                if home not in att or away not in att:
                    continue
                ph, pa = predict(att, con, home, away, k, h, base)
                err += (ph - mh) ** 2 + (pa - ma) ** 2
            if best is None or err < best[0]:
                best = (err, k, h)
    err, k, h = best
    rmse = (err / (2 * len(priced))) ** 0.5
    return k, h, round(rmse, 3)


def build(fixtures, teams, team_att, team_xgc, sent, med_att, med_xgc,
          odds_teams, events, med_xg_base=None):
    """Derived expected goals for every horizon fixture.

    Returns (per_team, meta) where per_team[short][event] = {'gf':x,'ga':y,
    'src':'odds'|'model'}.
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
    k, home_adv, rmse = calibrate(att, con, priced, base)

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
            gf_h, gf_a = predict(att, con, h, a, k, home_adv, base)
            src = 'model'
            n_model += 1
        per_team.setdefault(h, {})[ev] = {'gf': round(gf_h, 2), 'ga': round(gf_a, 2),
                                          'src': src, 'home': 1}
        per_team.setdefault(a, {})[ev] = {'gf': round(gf_a, 2), 'ga': round(gf_h, 2),
                                          'src': src, 'home': 0}
    # each team's own average expected goals across the season: the denominator
    # for turning a player's average-fixture rate into a this-fixture rate
    avg_gf = {}
    for c, evs in per_team.items():
        vals = [v['gf'] for v in evs.values()]
        avg_gf[c] = round(sum(vals) / len(vals), 3) if vals else base
    return per_team, {'k': k, 'home_adv': home_adv, 'rmse': rmse, 'base': base,
                      'avg_gf': avg_gf,
                      'priced': len(priced), 'odds_fixtures': n_odds,
                      'model_fixtures': n_model}
