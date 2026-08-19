"""Transfer and price momentum.

Two independent sources, so the useful parts work with no stored history:
  * per-gameweek net transfers (cumulative in the API — one read gives the
    week's whole flow) and FPL's own price-change projections;
  * optional snapshots, which add ownership/price deltas over time. Snapshots
    are best-effort: on an ephemeral container they simply reset, and the
    momentum view degrades to the no-history metrics rather than breaking.

Set FPL_DATA_DIR to a persistent path to keep snapshot history.
"""
import json
import os
from datetime import datetime, timezone

DATA_DIR = os.environ.get('FPL_DATA_DIR', 'data')
SNAP = os.path.join(DATA_DIR, 'snapshots.jsonl')


def snapshot(elements, teams, path=SNAP):
    """Append one compact row per interesting player. Cheap: ~200 rows/pull."""
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec='minutes')
        rows = []
        for e in elements.values():
            sel = float(e['selected_by_percent'])
            if sel < 0.4 and e['now_cost'] < 55:
                continue           # ignore the long tail nobody owns
            rows.append({'t': ts, 'i': e['id'], 'c': e['now_cost'], 's': sel,
                         'ti': e['transfers_in_event'], 'to': e['transfers_out_event']})
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(json.dumps(r, separators=(',', ':')) for r in rows) + '\n')
        return len(rows)
    except Exception:
        return 0


def _history(path=SNAP):
    """{player_id: [rows oldest-first]} from the snapshot log, if any."""
    hist = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                hist.setdefault(r['i'], []).append(r)
    except FileNotFoundError:
        return {}
    return hist


def history_stats(path=SNAP):
    """Rows and time span in the snapshot log — also the proof that whatever
    directory we're writing to actually persists across deployments."""
    rows, oldest, newest = 0, None, None
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                try:
                    t = json.loads(line)['t']
                except Exception:
                    continue
                rows += 1
                if oldest is None or t < oldest:
                    oldest = t
                if newest is None or t > newest:
                    newest = t
    except FileNotFoundError:
        pass
    return {'rows': rows, 'oldest': oldest, 'newest': newest, 'path': os.path.abspath(path)}


def momentum(players, elements, teams, top=12):
    """Rank transfer momentum. net = this gameweek's net transfers; where
    snapshot history exists, also ownership change since the oldest snapshot."""
    hist = _history()
    rows = []
    for p in players:
        e = elements.get(p['id'])
        if not e:
            continue
        tin, tout = e['transfers_in_event'], e['transfers_out_event']
        net = tin - tout
        sel = float(e['selected_by_percent'])
        try:
            pc = float(e.get('price_change_percent') or 0)
        except (TypeError, ValueError):
            pc = 0.0
        proj = e.get('price_change_projections') or []
        rise = 0.0
        for pr in proj[:1]:                     # tonight's projection
            try:
                rise = float(pr.get('likelihood') or 0)
            except (TypeError, ValueError):
                rise = 0.0
        h = hist.get(p['id']) or []
        d_sel = round(sel - h[0]['s'], 1) if h else None
        d_cost = round((e['now_cost'] - h[0]['c']) / 10, 1) if h else None
        span_h = None
        if len(h) > 1:
            try:
                a = datetime.fromisoformat(h[0]['t'])
                b = datetime.fromisoformat(h[-1]['t'])
                span_h = round((b - a).total_seconds() / 3600, 1)
            except Exception:
                span_h = None
        rows.append({
            'player': f"{p['name']}|{teams[p['team']]}", 'price': p['price'],
            'sel': sel, 'net': net, 'tin': tin, 'tout': tout,
            'pc': pc, 'rise_likelihood': rise, 'xpts': round(p.get('xpts', 0), 2),
            'xmins': round(p.get('xmins', 0)), 'd_sel': d_sel, 'd_cost': d_cost,
            'span_h': span_h,
        })
    # if the season hasn't started, net transfers are all zero — fall back to
    # ownership change so the view still says something useful
    live = any(r['net'] for r in rows)
    key = (lambda r: r['net']) if live else (lambda r: r['d_sel'] or 0)
    rows.sort(key=key, reverse=True)
    quiet = not live and not any(abs(r['d_sel'] or 0) >= 0.2 for r in rows)
    span = max((r['span_h'] or 0) for r in rows) if rows else 0
    return {'live': live, 'quiet': quiet, 'span_h': span,
            'in': [r for r in rows[:top] if key(r) > 0],
            'out': [r for r in sorted(rows, key=key)[:top] if key(r) < 0],
            'has_history': any(r['d_sel'] is not None for r in rows)}


def recent_moves(elements, teams, hours=6, top=6, min_pp=0.15):
    """Ownership/transfer movement over roughly the last `hours`, from snapshot
    history. Returns (risers, fallers, meta) — empty until enough baseline."""
    hist = _history()
    if not hist:
        return [], [], {'ready': False, 'hours': 0}
    stamps = sorted({r['t'] for rows in hist.values() for r in rows})
    if len(stamps) < 2:
        return [], [], {'ready': False, 'hours': 0}
    newest = stamps[-1]
    try:
        cutoff = datetime.fromisoformat(newest).timestamp() - hours * 3600
        older = [s for s in stamps if datetime.fromisoformat(s).timestamp() <= cutoff]
        base = older[-1] if older else stamps[0]
        span = round((datetime.fromisoformat(newest).timestamp()
                      - datetime.fromisoformat(base).timestamp()) / 3600, 1)
    except Exception:
        base, span = stamps[0], 0.0
    moves = []
    for pid, rows in hist.items():
        e = elements.get(pid)
        if not e:
            continue
        cur = next((r for r in reversed(rows) if r['t'] == newest), None)
        old = next((r for r in reversed(rows) if r['t'] == base), None)
        if not cur or not old:
            continue
        d_sel = round(cur['s'] - old['s'], 2)
        d_net = (cur['ti'] - cur['to']) - (old['ti'] - old['to'])
        if abs(d_sel) < min_pp and d_net == 0:
            continue
        moves.append({'player': f"{e['web_name']}|{teams[e['team']]}",
                      'price': cur['c'] / 10, 'sel': cur['s'],
                      'd_sel': d_sel, 'd_net': d_net,
                      'd_cost': round((cur['c'] - old['c']) / 10, 1)})
    key = (lambda m: (m['d_net'], m['d_sel']))
    risers = sorted([m for m in moves if key(m) > (0, 0)], key=key, reverse=True)[:top]
    fallers = sorted([m for m in moves if key(m) < (0, 0)], key=key)[:top]
    return risers, fallers, {'ready': True, 'hours': span, 'snapshots': len(stamps)}


def correlate(mom, news_payload, top=8):
    """Join momentum with the news sweep: is the market reacting to a story, or
    moving with no visible catalyst?"""
    flagged = {}
    if news_payload:
        for key, items in (news_payload.get('players') or {}).items():
            flagged[key] = items[0]
        for d in (news_payload.get('discoveries') or []):
            flagged.setdefault(d['player'], d['items'][0] if d.get('items') else None)
    out = []
    for r in mom['in'][:top]:
        item = flagged.get(r['player'])
        out.append({**r, 'explained': bool(item),
                    'headline': (item or {}).get('title', ''),
                    'source': (item or {}).get('source', '')})
    return out
