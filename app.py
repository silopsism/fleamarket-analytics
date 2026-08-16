"""Fleamarket Analytics server.

Serves the static dashboard plus /team/{id}: paste any FPL team ID and get
that squad analyzed against the xPts model. Run:  uvicorn app:app --host
0.0.0.0 --port 8000
"""
import json
import os
import time
import urllib.request

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

app = FastAPI(title='Fleamarket Analytics')
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}
_cache = {'ts': 0.0, 'players': None, 'teams': None, 'events': None}


def fpl_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def model_data():
    """Players scored by model.py; recomputed when bootstrap.json changes or 6h pass."""
    mtime = os.path.getmtime('bootstrap.json')
    if _cache['players'] is None or mtime > _cache['ts'] or time.time() - _cache['ts'] > 21600:
        src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
        ns = {}
        exec(compile(src, 'model.py', 'exec'), ns)
        boot = json.load(open('bootstrap.json', encoding='utf-8'))
        _cache.update(ts=mtime, players={p['id']: p for p in ns['players']},
                      teams=ns['teams'], events=boot['events'],
                      elements={e['id']: e for e in boot['elements']})
    return _cache


PAGE = """<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:light dark;--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;
--muted:#898781;--grid:#e1e0d9;--ring:rgba(11,11,11,.10);--accent:#4a3aa7;--warn:#d03b3b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;
--ink2:#c3c2b7;--grid:#2c2c2a;--ring:rgba(255,255,255,.10);--accent:#9085e9;--warn:#e66767}}}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:28px 20px 60px}}
.wrap{{max-width:760px;margin:0 auto}}
.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}}
h1{{font-size:clamp(22px,4vw,32px);letter-spacing:-.02em;margin-bottom:4px}}
.sub{{color:var(--ink2);margin-bottom:20px}}
.card{{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:20px;margin-top:18px}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid)}}
td{{padding:6px 8px;border-bottom:1px solid var(--grid);font-size:13.5px}}
td.num,th.num{{text-align:right}}
.low{{color:var(--warn);font-weight:700}}
form{{display:flex;gap:8px;margin-top:8px}}
input{{flex:1;padding:9px 12px;border:1px solid var(--grid);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}}
button{{padding:9px 16px;border:none;border-radius:8px;background:var(--accent);color:#fff;font:600 14px system-ui;cursor:pointer}}
a{{color:var(--accent)}}
.note{{font-size:12.5px;color:var(--muted);margin-top:10px}}
</style>
<div class="wrap">
<div class="eyebrow">Fleamarket Analytics</div>
{body}
<p class="note"><a href="/">← Dashboard</a> · Scores are model xPts/match from prior-season
Opta rates — a value lens, not an oracle.</p>
</div>"""

FORM = """<h1>Analyze any team</h1>
<p class="sub">Paste an FPL team ID (from the Points page URL: fantasy.premierleague.com/entry/<b>ID</b>/…).</p>
<div class="card"><form action="/team" method="get" onsubmit="location='/team/'+document.getElementById('tid').value;return false">
<input id="tid" inputmode="numeric" pattern="[0-9]*" placeholder="e.g. 437580" required>
<button>Analyze</button></form></div>"""


@app.get('/', response_class=HTMLResponse)
def home():
    if os.path.exists('dashboard.html'):
        return FileResponse('dashboard.html')
    return PAGE.format(title='Fleamarket Analytics', body=FORM)


@app.get('/team', response_class=HTMLResponse)
@app.get('/team/', response_class=HTMLResponse)
def team_form():
    return PAGE.format(title='Analyze a team', body=FORM)


@app.get('/team/{team_id}', response_class=HTMLResponse)
def team(team_id: int):
    m = model_data()
    try:
        entry = fpl_get(f'https://fantasy.premierleague.com/api/entry/{team_id}/')
    except Exception:
        return PAGE.format(title='Not found', body='<h1>Team not found</h1>'
                           '<p class="sub">Check the ID and try again.</p>' + FORM)
    name = entry.get('name', '?')
    manager = f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip()
    gw = next((e['id'] for e in m['events'] if e['is_current']), None) \
        or max((e['id'] for e in m['events'] if e['finished']), default=None)

    picks = None
    if gw:
        try:
            picks = fpl_get(f'https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/')
        except Exception:
            picks = None
    if not picks or 'picks' not in picks:
        body = (f'<h1>{name}</h1><p class="sub">{manager}</p>'
                '<div class="card"><p>Picks are private until the gameweek deadline passes — '
                'FPL only publishes each squad once it locks. Check back after the deadline.</p></div>')
        return PAGE.format(title=name, body=body)

    rows, xi_total, flagged = [], 0.0, []
    pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    for pk in picks['picks']:
        el = m['elements'].get(pk['element'])
        mp = m['players'].get(pk['element'])
        xp = mp['xpts'] if mp else 0.0
        is_xi = pk['position'] <= 11
        if is_xi:
            xi_total += xp * pk['multiplier'] if pk['multiplier'] else xp
        cap = ' (C)' if pk['is_captain'] else (' (V)' if pk['is_vice_captain'] else '')
        low = is_xi and xp < 2.4
        if low and el:
            flagged.append((el, xp))
        rows.append(f"<tr><td>{'XI' if is_xi else 'bench'}</td><td><b>{el['web_name']}{cap}</b></td>"
                    f"<td>{m['teams'][el['team']]}</td><td>{pos_name[el['element_type']]}</td>"
                    f"<td class='num'>{el['now_cost']/10:.1f}</td>"
                    f"<td class='num {'low' if low else ''}'>{xp:.2f}</td></tr>")

    sugg = ''
    if flagged:
        items = []
        for el, xp in flagged[:3]:
            price = el['now_cost'] / 10
            alts = sorted((p for p in m['players'].values()
                           if p['pos'] == el['element_type'] and p['price'] <= price + 0.5
                           and p['xpts'] > xp + 0.8), key=lambda p: -p['xpts'])[:3]
            if alts:
                names = ', '.join(f"{a['name']} (£{a['price']:.1f}, {a['xpts']:.2f})" for a in alts)
                items.append(f"<li><b>{el['web_name']}</b> ({xp:.2f}) → {names}</li>")
        if items:
            sugg = ('<div class="card"><h2 style="font-size:16px">Upgrade ideas</h2>'
                    '<p class="note" style="margin:2px 0 10px">Same position, within £0.5m, ranked by model score.</p>'
                    f"<ul style='padding-left:20px'>{''.join(items)}</ul></div>")

    body = (f'<h1>{name}</h1><p class="sub">{manager} · GW{gw} squad · XI model score '
            f'<b>{xi_total:.1f}</b> xPts (captain doubled)</p>'
            '<div class="card"><table><tr><th></th><th>Player</th><th>Team</th><th>Pos</th>'
            '<th class="num">£m</th><th class="num">xPts</th></tr>'
            + ''.join(rows) + '</table></div>' + sugg)
    return PAGE.format(title=name, body=body)
