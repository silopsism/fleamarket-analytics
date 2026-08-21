"""A single model-run entry, tracked through the season under the real rules.

Recomputing a fresh "optimal squad" every week produces a team that could never
legally exist - it ignores that you arrive at each gameweek owning something,
with one free transfer and a fixed budget. Its season total means nothing.

So instead we freeze ONE squad at GW1 and play it out: one free transfer a week
(bankable to five), -4 a hit, selling prices rather than market prices, and the
points it actually scored including autosubs and the captain. That is a
benchmark our own team can be compared against honestly.

State lives in data/model_entry.json - the persistent volume, already gitignored,
so nothing about it reaches the public repo.

    python paper.py init      # freeze the current model optimum as GW1
    python paper.py advance   # decide this week's transfers, XI and captain
    python paper.py score     # record what the locked lineup actually scored
    python paper.py show      # the ledger so far
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

STATE = os.path.join('data', 'model_entry.json')
LIVE = 'https://fantasy.premierleague.com/api/event/%d/live/'
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}

# a valid XI: exactly one keeper, and these bounds on the rest
XI_MIN = {1: 1, 2: 3, 3: 2, 4: 1}
XI_MAX = {1: 1, 2: 5, 3: 5, 4: 3}
FT_BANK_MAX = 5


def sell_price(buy, now):
    """FPL sells a risen player at purchase price plus HALF the rise, rounded
    down to the nearest 0.1; a fallen player sells at his current price. All in
    tenths of a million, which is how the API stores them."""
    return buy + (now - buy) // 2 if now > buy else now


def load(path=STATE):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save(state, path=STATE):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    return state


def _now(boot):
    return {e['id']: e['now_cost'] for e in boot['elements']}


def squad_budget(state, boot):
    """Selling value of the squad plus the bank, in tenths."""
    now = _now(boot)
    return (sum(sell_price(p['buy'], now.get(p['id'], p['buy'])) for p in state['squad'])
            + state['bank'])


def init(players, boot, optimal_path='optimal_squad.json', start_gw=None,
         path=STATE, force=False):
    """Freeze the current model optimum as the entry's GW1 squad.

    Purchase prices are today's prices, which is what a manager who built this
    squad now would have paid - so it must be run before prices start moving.
    """
    if load(path) and not force:
        raise SystemExit('entry already exists; pass force=True to restart it')
    opt = json.load(open(optimal_path, encoding='utf-8'))
    teams = {t['id']: t['short_name'] for t in boot['teams']}
    lookup = {(p['name'], teams[p['team']]): p for p in players}
    by_id = {p['id']: p for p in players}

    squad, xi, cap = [], [], None
    for line, role in zip(opt['lines'], opt['roles']):
        name, club = line.rsplit(' ', 1)
        p = lookup.get((name, club))
        if p is None:
            raise SystemExit(f'cannot resolve {line!r} against the model')
        squad.append({'id': p['id'], 'name': p['name'], 'club': club,
                      'pos': p['pos'], 'buy': int(round(p['price'] * 10))})
        if role in ('X', 'C'):
            xi.append(p['id'])
        if role == 'C':
            cap = p['id']
    if len(xi) != 11 or cap is None:
        raise SystemExit(f'optimum did not describe a legal XI (roles={opt["roles"]})')

    # bench in autosub order (keeper first, then by projection) and the vice as
    # the best remaining starter - both by this gameweek's number, not season-long
    def xnext(pid):
        return by_id[pid]['gws'][0] if pid in by_id else 0.0

    pos_of = {p['id']: p['pos'] for p in squad}
    bench_ids = [p['id'] for p in squad if p['id'] not in xi]
    bench = ([i for i in bench_ids if pos_of[i] == 1]
             + sorted((i for i in bench_ids if pos_of[i] != 1), key=lambda i: -xnext(i)))
    vice = max((i for i in xi if i != cap), key=xnext)
    gw = start_gw or min(e['id'] for e in boot['events'] if not e['finished'])
    spent = sum(p['buy'] for p in squad)
    state = {
        'created': datetime.now(timezone.utc).isoformat(timespec='minutes'),
        'name': 'Model entry',
        'start_gw': gw,
        'squad': squad,
        'xi': xi, 'bench': bench, 'cap': cap, 'vice': vice,
        'bank': 1000 - spent,
        'ft': 1,
        'history': [],
        'locked_gw': gw,          # the gameweek the current lineup is locked for
    }
    # the opening gameweek is a locked decision like any other, so it gets a
    # history row straight away - otherwise there is nothing for score() to fill
    state['history'].append({
        'gw': gw, 'xi': xi, 'bench': bench, 'cap': cap, 'vice': vice,
        'transfers': {'in': [], 'out': [], 'in_ids': [], 'out_ids': [], 'hits': 0},
        'ft_after': 1, 'bank': state['bank'], 'value': 1000,
        'projected': round(sum(xnext(i) for i in xi) + xnext(cap), 2),
        'points': None,
    })
    return save(state, path)


def _pick_lineup(plan_squad, players_by_id):
    """Pull the XI, bench order and captain out of a solved plan's week 0."""
    xi = [s['id'] for s in plan_squad if s['xi']]
    cap = next((s['id'] for s in plan_squad if s['cap']), None)
    bench = [s['id'] for s in plan_squad if not s['xi']]
    # bench order: keeper first, then by projection, which is the autosub order
    gk = [i for i in bench if players_by_id[i]['pos'] == 1]
    rest = sorted((i for i in bench if players_by_id[i]['pos'] != 1),
                  key=lambda i: -players_by_id[i]['gws'][0])
    vice = max((i for i in xi if i != cap),
               key=lambda i: players_by_id[i]['gws'][0], default=None)
    return xi, gk + rest, cap, vice


def advance(players, boot, gw=None, path=STATE, time_limit=120, n_gw=4):
    """Decide the upcoming gameweek: transfers, XI, captain. Idempotent per gw."""
    import plan4
    state = load(path)
    if not state:
        raise SystemExit('no entry yet - run init first')
    gw = gw or min(e['id'] for e in boot['events'] if not e['finished'])
    if state.get('locked_gw') == gw:
        return state, None            # already decided for this gameweek

    by_id = {p['id']: p for p in players}
    now = _now(boot)
    sells = {p['id']: sell_price(p['buy'], now.get(p['id'], p['buy'])) / 10
             for p in state['squad']}
    owned = [p['id'] for p in state['squad']]
    budget = squad_budget(state, boot) / 10

    plan = plan4.solve_plan(players, n_gw=n_gw, budget=budget, time_limit=time_limit,
                            initial_ids=owned, initial_ft=state['ft'],
                            transfer_before_first=True, sell_prices=sells)
    if not plan:
        raise SystemExit('solver found no plan')
    pool = plan['pool']
    move = next((t for t in plan['transfers'] if t.get('gw_index') == 0),
                {'in': [], 'out': [], 'hits': 0})

    out_names = {p['id']: p['name'] for p in state['squad'] if p['id'] in move['out']}
    # apply it: sold players release their SELLING price, bought players cost market
    for pid in move['out']:
        rec = next(p for p in state['squad'] if p['id'] == pid)
        state['bank'] += sell_price(rec['buy'], now.get(pid, rec['buy']))
        state['squad'].remove(rec)
    for pid in move['in']:
        p = by_id[pid]
        state['bank'] -= int(round(p['price'] * 10))
        state['squad'].append({'id': pid, 'name': p['name'],
                               'club': boot and next(t['short_name'] for t in boot['teams']
                                                     if t['id'] == p['team']),
                               'pos': p['pos'], 'buy': int(round(p['price'] * 10))})
    if state['bank'] < 0:
        raise SystemExit(f"plan overspent by {-state['bank']/10:.1f}m - not applied")

    used, hits = len(move['in']), move['hits']
    state['ft'] = min(state['ft'] - (used - hits) + 1, FT_BANK_MAX)

    xi, bench, cap, vice = _pick_lineup(plan['gws'][0], {i: pool[i] for i in pool})
    state.update({'xi': xi, 'bench': bench, 'cap': cap, 'vice': vice, 'locked_gw': gw})
    state['history'].append({
        'gw': gw, 'xi': xi, 'bench': bench, 'cap': cap, 'vice': vice,
        'transfers': {'in': [by_id[i]['name'] for i in move['in']],
                      'out': [out_names.get(i, str(i)) for i in move['out']],
                      'in_ids': move['in'], 'out_ids': move['out'], 'hits': hits},
        'ft_after': state['ft'], 'bank': state['bank'],
        'value': squad_budget(state, boot),
        'projected': round(sum(pool[i]['gws'][0] for i in xi)
                           + (pool[cap]['gws'][0] if cap in pool else 0) - 4 * hits, 2),
        'points': None,
    })
    return save(state, path), move


def _live(gw):
    req = urllib.request.Request(LIVE % gw, headers=UA)
    raw = urllib.request.urlopen(req, timeout=30).read()
    data = json.loads(raw)
    return {e['id']: e['stats'] for e in data['elements']}


def apply_autosubs(xi, bench, squad_pos, mins):
    """FPL autosubs: a starter on zero minutes is replaced by the first bench
    player who played, provided the XI stays a legal formation. The keeper only
    ever swaps with the keeper. Returns (final_xi, [(out, in), ...])."""
    final, subs = list(xi), []
    pending = [i for i in bench]
    for out in list(final):
        if mins.get(out, 0) > 0:
            continue
        for cand in list(pending):
            if mins.get(cand, 0) <= 0:
                continue
            if (squad_pos[out] == 1) != (squad_pos[cand] == 1):
                continue                      # keeper for keeper only
            trial = [i for i in final if i != out] + [cand]
            counts = {}
            for i in trial:
                counts[squad_pos[i]] = counts.get(squad_pos[i], 0) + 1
            if all(XI_MIN[p] <= counts.get(p, 0) <= XI_MAX[p] for p in XI_MIN):
                final = trial
                pending.remove(cand)
                subs.append((out, cand))
                break
    return final, subs


def score(gw=None, path=STATE, live=None):
    """Record what the locked lineup actually scored for a finished gameweek."""
    state = load(path)
    if not state:
        raise SystemExit('no entry yet')
    gw = gw or state.get('locked_gw')
    entry = next((h for h in state['history'] if h['gw'] == gw), None)
    if entry is None:
        raise SystemExit(f'gameweek {gw} was never locked in')
    stats = live if live is not None else _live(gw)
    mins = {i: (stats.get(i) or {}).get('minutes', 0) for i in entry['xi'] + entry['bench']}
    pts = {i: (stats.get(i) or {}).get('total_points', 0) for i in entry['xi'] + entry['bench']}
    pos = {p['id']: p['pos'] for p in state['squad']}
    for i in entry['xi'] + entry['bench']:      # transferred-out players still need a pos
        pos.setdefault(i, 3)

    final_xi, subs = apply_autosubs(entry['xi'], entry['bench'], pos, mins)
    # the armband falls to the vice if the captain did not play
    cap = entry['cap'] if mins.get(entry['cap'], 0) > 0 else entry['vice']
    total = sum(pts.get(i, 0) for i in final_xi)
    total += pts.get(cap, 0) if cap in final_xi else 0
    total -= 4 * entry['transfers']['hits']

    entry.update({'points': total, 'autosubs': subs,
                  'captain_used': cap, 'bench_points': sum(
                      pts.get(i, 0) for i in entry['bench'] if i not in final_xi)})
    return save(state, path), entry


def summary(path=STATE):
    state = load(path)
    if not state:
        return None
    scored = [h for h in state['history'] if h['points'] is not None]
    return {'gws': len(scored),
            'points': sum(h['points'] for h in scored),
            'hits': sum(h['transfers']['hits'] for h in scored) * 4,
            'value': state['history'][-1]['value'] if state['history'] else None,
            'bank': state['bank'], 'ft': state['ft'],
            'locked_gw': state.get('locked_gw')}


def _model():
    src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
    ns = {'__name__': 'paper'}
    exec(compile(src, 'model.py', 'exec'), ns)
    return ns['players'], ns['d']


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    if cmd == 'init':
        players, boot = _model()
        st = init(players, boot, force='--force' in sys.argv)
        print(f"frozen GW{st['start_gw']}: {len(st['squad'])} players, "
              f"bank {st['bank']/10:.1f}m, ft {st['ft']}")
        for p in st['squad']:
            tag = 'C' if p['id'] == st['cap'] else ('V' if p['id'] == st['vice'] else
                                                    ('XI' if p['id'] in st['xi'] else 'bench'))
            print(f"  {tag:5} {p['name']:16}{p['club']:5}£{p['buy']/10:4.1f}")
    elif cmd == 'advance':
        players, boot = _model()
        st, move = advance(players, boot)
        if move is None:
            print(f"already locked for GW{st['locked_gw']}")
        else:
            h = st['history'][-1]
            print(f"GW{h['gw']}: {len(move['in'])} transfer(s), {move['hits']} hit(s), "
                  f"ft left {st['ft']}, bank {st['bank']/10:.1f}m, "
                  f"projected {h['projected']}")
            for a, b in zip(h['transfers']['out_ids'], h['transfers']['in_ids']):
                print(f"   OUT {a} -> IN {b}")
    elif cmd == 'score':
        gw = int(sys.argv[2]) if len(sys.argv) > 2 else None
        st, entry = score(gw)
        print(f"GW{entry['gw']}: {entry['points']} pts "
              f"(projected {entry['projected']}, bench {entry['bench_points']}, "
              f"autosubs {entry['autosubs']})")
    else:
        s = summary()
        if not s:
            print('no entry yet - run: python paper.py init')
        else:
            print(json.dumps(s, indent=1))
            st = load()
            for h in st['history']:
                print(f"  GW{h['gw']}: projected {h['projected']} "
                      f"actual {h['points'] if h['points'] is not None else '-'} "
                      f"hits {h['transfers']['hits']} value {h['value']/10:.1f}m")
