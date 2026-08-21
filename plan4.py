"""Multi-period squad optimizer: best 15 + weekly XI + captain + transfer plan
over the model horizon (4 GWs), as a mixed-integer program.

Rules encoded: £100m budget every week, 2/5/5/3 quotas, max 3 per club,
formation bounds per week, one free transfer earned per week (bankable, cap 3),
extra transfers cost a 4-point hit (max `max_hits` over the horizon), transfers
are like-for-like by position.

The player pool is pruned to keep CBC fast: top scorers per position plus the
cheapest playing enablers.
"""
import pulp

POS_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}
# A free transfer is not free. Its value is the flexibility it buys beyond the
# horizon - reacting to an injury, a price rise, a fixture swing we cannot see
# yet - so spending one has to clear a bar. FPL Review's solver defaults this to
# 1.75 and calls 2.0 the commonly recommended baseline, the setting that makes a
# solver skip marginal moves and keep transfers for later; below ~1.0 it churns
# the squad for fractions of a point. Charged per transfer that consumes a free
# transfer, so a points-hit transfer still costs 4 and not 4 plus this.
# It is a PLANNING cost, not a real deduction - you do not lose 2 points by
# transferring, so it must never be folded into a displayed points total.
FT_VALUE = 2.0
FT_BANK_MAX = 5        # FPL banks up to five, not three
XI_MIN = {1: 1, 2: 3, 3: 2, 4: 1}
XI_MAX = {1: 1, 2: 5, 3: 5, 4: 3}
POOL_TOP = {1: 8, 2: 22, 3: 28, 4: 16}


def solve_plan(players, n_gw=4, budget=100.0, max_hits=4, time_limit=90,
               initial_ids=None, force_ids=None, ft_value=FT_VALUE, initial_ft=1,
               transfer_before_first=False, sell_prices=None):
    """Best squad + weekly XI/captain + transfer plan over the horizon.

    initial_ids: fix the first gameweek's 15 to an existing squad, turning this
    into "what should THIS team do next" instead of "what is the best team".
    force_ids: require these players in every gameweek's 15. Solve with and
    without to price what keeping a particular player costs.
    ft_value: points charged for each free transfer spent (see FT_VALUE).
    initial_ft: free transfers already banked at the first opportunity.
    transfer_before_first: allow transfers INTO the first horizon gameweek. The
        default answers "what should this squad do from here", holding the first
        week fixed; True answers "it is between gameweeks, what do I do now",
        which is what a season-long tracked entry needs each week.
    sell_prices: {player_id: selling price} for an owned squad. FPL sells a
        risen player at purchase price plus half the rise, so squad value is not
        the sum of current prices. Ignored for players not owned.
    """
    pool = {}
    for pos, top in POOL_TOP.items():
        cand = [p for p in players if p['pos'] == pos and p['xmins'] >= 45 and p['tot4'] > 0]
        for p in sorted(cand, key=lambda p: -p['tot4'])[:top]:
            pool[p['id']] = p
        for p in sorted(cand, key=lambda p: p['price'])[:4]:  # cheap enablers
            pool[p['id']] = p
    by_id = {p['id']: p for p in players}
    for pid in list(initial_ids or []) + list(force_ids or []):
        if pid in by_id:
            pool[pid] = by_id[pid]          # owned/forced players must be selectable
    P = list(pool.values())
    G = list(range(n_gw))

    prob = pulp.LpProblem('plan4', pulp.LpMaximize)
    sq = {(p['id'], g): pulp.LpVariable(f"s{p['id']}_{g}", cat='Binary') for p in P for g in G}
    xi = {(p['id'], g): pulp.LpVariable(f"x{p['id']}_{g}", cat='Binary') for p in P for g in G}
    cp = {(p['id'], g): pulp.LpVariable(f"c{p['id']}_{g}", cat='Binary') for p in P for g in G}
    TG = list(G) if (initial_ids and transfer_before_first) else list(G[1:])
    tin = {(p['id'], g): pulp.LpVariable(f"i{p['id']}_{g}", cat='Binary') for p in P for g in TG}
    tout = {(p['id'], g): pulp.LpVariable(f"o{p['id']}_{g}", cat='Binary') for p in P for g in TG}
    ft = {g: pulp.LpVariable(f'ft{g}', lowBound=0, upBound=FT_BANK_MAX) for g in TG}
    hits = {g: pulp.LpVariable(f'h{g}', lowBound=0, upBound=max_hits, cat='Integer') for g in TG}

    owned0 = set(initial_ids or [])

    def cost(p, g):
        """What this player counts against the budget in gameweek g: his selling
        price while still owned from the start, his market price once bought."""
        if g == 0 and sell_prices and p['id'] in sell_prices:
            return sell_prices[p['id']]
        return p['price']

    for g in G:
        for pos, n in POS_QUOTA.items():
            prob += pulp.lpSum(sq[p['id'], g] for p in P if p['pos'] == pos) == n
        prob += pulp.lpSum(cost(p, g) * sq[p['id'], g] for p in P) <= budget
        clubs = {}
        for p in P:
            clubs.setdefault(p['team'], []).append(p)
        for members in clubs.values():
            prob += pulp.lpSum(sq[m['id'], g] for m in members) <= 3
        prob += pulp.lpSum(xi[p['id'], g] for p in P) == 11
        prob += pulp.lpSum(cp[p['id'], g] for p in P) == 1
        for pos in POS_QUOTA:
            n_pos = pulp.lpSum(xi[p['id'], g] for p in P if p['pos'] == pos)
            prob += n_pos >= XI_MIN[pos]
            prob += n_pos <= XI_MAX[pos]
        for p in P:
            prob += xi[p['id'], g] <= sq[p['id'], g]
            prob += cp[p['id'], g] <= xi[p['id'], g]

    if initial_ids and 0 in TG:
        # between gameweeks: the squad may change on the way into week 0
        for p in P:
            prob += (sq[p['id'], 0] == (1 if p['id'] in owned0 else 0)
                     + tin[p['id'], 0] - tout[p['id'], 0])
    elif initial_ids:
        for p in P:
            prob += sq[p['id'], 0] == (1 if p['id'] in owned0 else 0)

    for pid in (force_ids or []):
        if pid in pool:
            for g in G:
                prob += sq[pid, g] == 1

    for g in G[1:]:
        for p in P:
            prob += sq[p['id'], g] == sq[p['id'], g - 1] + tin[p['id'], g] - tout[p['id'], g]

    for i, g in enumerate(TG):
        # like-for-like: transfers balance within each position
        for pos in POS_QUOTA:
            prob += (pulp.lpSum(tin[p['id'], g] for p in P if p['pos'] == pos)
                     == pulp.lpSum(tout[p['id'], g] for p in P if p['pos'] == pos))
        n_g = pulp.lpSum(tin[p['id'], g] for p in P)
        prob += hits[g] >= n_g - ft[g]
        prob += hits[g] <= n_g
        if i == 0:
            prob += ft[g] == initial_ft
        else:
            # '<=' rather than '==' so hitting the bank cap forfeits the surplus,
            # as the real rules do, instead of making the program infeasible
            prev = TG[i - 1]
            prob += ft[g] <= ft[prev] - (pulp.lpSum(tin[p['id'], prev] for p in P)
                                         - hits[prev]) + 1
    prob += pulp.lpSum(hits.values()) <= max_hits

    # free transfers spent = transfers made, less the ones taken as hits
    ft_spent = pulp.lpSum(tin[p['id'], g] for p in P for g in TG) - pulp.lpSum(hits.values())
    prob += (pulp.lpSum(p['gws'][g] * (xi[p['id'], g] + cp[p['id'], g]) for p in P for g in G)
             - 4 * pulp.lpSum(hits.values())
             - ft_value * ft_spent)

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    if pulp.LpStatus[prob.status] not in ('Optimal', 'Not Solved'):
        return None

    def val(v):
        return v.value() or 0

    gws_out, transfers = [], []
    for g in G:
        squad = []
        for p in P:
            if val(sq[p['id'], g]) > 0.5:
                squad.append({'id': p['id'], 'xi': val(xi[p['id'], g]) > 0.5,
                              'cap': val(cp[p['id'], g]) > 0.5})
        gws_out.append(squad)
        if g in TG:
            moves = {'gw_index': g,
                     'in': [p['id'] for p in P if val(tin[p['id'], g]) > 0.5],
                     'out': [p['id'] for p in P if val(tout[p['id'], g]) > 0.5],
                     'hits': int(round(val(hits[g])))}
            transfers.append(moves)
    return {'gws': gws_out, 'transfers': transfers, 'pool': {p['id']: p for p in P},
            'status': pulp.LpStatus[prob.status]}
