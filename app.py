"""Fleamarket Analytics server.

Serves the static dashboard plus /team/{id}: paste any FPL team ID and get
that squad analyzed against the xPts model. Run:  uvicorn app:app --host
0.0.0.0 --port 8000
"""
import difflib
import json
import os
import re
import time
import unicodedata
import urllib.request

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

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
<button>Analyze</button></form>
<p class="note">Deadline not passed yet, so squads are still private? <a href="/paste">Paste your squad manually →</a></p></div>"""

PASTE_FORM = """<h1>Paste your squad</h1>
<p class="sub">One player per line (or comma-separated). Accents optional — <i>Guehi</i>,
<i>Le Fee</i> and <i>Joao Pedro</i> all work. Mark your captain with <b>(c)</b>.
If two players share a name, add the club: <i>Sangare NFO</i>.</p>
<div class="card"><form action="/paste" method="get">
<textarea name="squad" rows="16" required placeholder="Kinsky
Guehi
Maguire
Bruno Fernandes
Joao Pedro (c)
…" style="width:100%;padding:10px 12px;border:1px solid var(--grid);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit;resize:vertical"></textarea>
<div style="margin-top:10px;display:flex;justify-content:flex-end"><button>Analyze</button></div>
</form></div>"""


def norm(s):
    s = unicodedata.normalize('NFKD', s.lower())
    return ''.join(ch for ch in s if not unicodedata.combining(ch))


def match_line(line, m):
    """Resolve one pasted line to an element. Returns (element|None, note)."""
    raw = line.strip().strip(',').strip()
    is_cap = bool(re.search(r'\(\s*c\s*\)', raw, re.I))
    raw = re.sub(r'\(\s*c\s*\)', '', raw, flags=re.I).strip()
    if not raw:
        return None, None, False
    team_filter = None
    words = raw.split()
    team_by_short = {norm(v): k for k, v in m['teams'].items()}
    if len(words) > 1 and norm(words[-1]) in team_by_short:
        team_filter = team_by_short[norm(words[-1])]
        raw = ' '.join(words[:-1])
    q = norm(raw)
    els = [e for e in m['elements'].values()
           if team_filter is None or e['team'] == team_filter]
    exact = [e for e in els if norm(e['web_name']) == q]
    if len(exact) == 1:
        return exact[0], None, is_cap
    qtok = set(q.split())
    sub = [e for e in els if q in norm(e['web_name'])
           or q in norm(f"{e['first_name']} {e['second_name']}")
           or qtok <= set(norm(f"{e['first_name']} {e['second_name']}").split())]
    if len(exact) > 1 or len(sub) > 1:
        opts = ', '.join(f"{e['web_name']} {m['teams'][e['team']]}" for e in (exact or sub)[:4])
        return None, f'ambiguous — did you mean: {opts}? (add the club, e.g. “{raw} {m["teams"][(exact or sub)[0]["team"]]}”)', is_cap
    if len(sub) == 1:
        return sub[0], None, is_cap
    close = difflib.get_close_matches(q, [norm(e['web_name']) for e in els], n=3, cutoff=0.7)
    if close:
        names = ', '.join(sorted({e['web_name'] for e in els if norm(e['web_name']) in close}))
        return None, f'not found — closest: {names}', is_cap
    return None, 'not found', is_cap


@app.get('/paste', response_class=HTMLResponse)
def paste(squad: str = ''):
    if not squad.strip():
        return PAGE.format(title='Paste your squad', body=PASTE_FORM)
    m = model_data()
    pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    rows, problems, total, seen = [], [], 0.0, set()
    lines = [ln for chunk in squad.splitlines() for ln in chunk.split(',')]
    for ln in lines:
        el, note, is_cap = match_line(ln, m)
        if el is None:
            if note:
                problems.append(f'<li><b>{ln.strip()}</b>: {note}</li>')
            continue
        if el['id'] in seen:
            continue
        seen.add(el['id'])
        mp = m['players'].get(el['id'])
        xp = mp['xpts'] if mp else 0.0
        total += xp * (2 if is_cap else 1)
        low = xp < 2.4
        flag = ' ⚠ ' + el['news'][:36] if el['status'] not in ('a',) else ''
        rows.append((el['element_type'], f"<tr><td><b>{el['web_name']}{' (C)' if is_cap else ''}</b>{flag}</td>"
                     f"<td>{m['teams'][el['team']]}</td><td>{pos_name[el['element_type']]}</td>"
                     f"<td class='num'>{el['now_cost']/10:.1f}</td>"
                     f"<td class='num {'low' if low else ''}'>{xp:.2f}</td></tr>"))
    rows.sort(key=lambda r: r[0])
    prob_html = (f"<div class='card'><b>Couldn’t match {len(problems)} line(s)</b>"
                 f"<ul style='padding-left:20px;margin-top:6px'>{''.join(problems)}</ul></div>") if problems else ''
    body = (f'<h1>Pasted squad — {len(rows)} matched</h1>'
            f'<p class="sub">Combined model score <b>{total:.1f}</b> xPts/match'
            f'{" (captain doubled)" if "(C)" in "".join(r[1] for r in rows) else ""}.'
            f' Red = weak by model. <a href="/paste">Edit / start over</a></p>'
            '<div class="card"><table><tr><th>Player</th><th>Team</th><th>Pos</th>'
            '<th class="num">£m</th><th class="num">xPts</th></tr>'
            + ''.join(r[1] for r in rows) + '</table></div>' + prob_html)
    return PAGE.format(title='Pasted squad', body=body)


ANALYZER_BANNER = """<section class="card" style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;margin-top:0">
<div><b>Analyze any team</b><br><span style="font-size:13px;color:var(--ink2)">Paste an FPL team ID and see that squad scored by the model — works for friends' teams too.</span></div>
<a href="/team" style="background:var(--accent);color:#fff;text-decoration:none;font:600 14px system-ui;padding:9px 16px;border-radius:8px;white-space:nowrap">Open analyzer →</a>
</section>"""


@app.get('/', response_class=HTMLResponse)
def home():
    if os.path.exists('dashboard.html'):
        html = open('dashboard.html', encoding='utf-8').read()
        # inject the analyzer banner right after the page header (server-only:
        # the static/artifact copy of dashboard.html stays unchanged)
        return HTMLResponse(html.replace('</header>', '</header>' + ANALYZER_BANNER, 1))
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
                'FPL only publishes each squad once it locks. Check back after the deadline, '
                'or <a href="/paste">paste your squad manually</a> to analyze it now.</p></div>')
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
