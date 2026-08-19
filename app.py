"""Fleamarket Analytics server.

Serves the static dashboard plus /team/{id}: paste any FPL team ID and get
that squad analyzed against the xPts model. Run:  uvicorn app:app --host
0.0.0.0 --port 8000
"""
import difflib
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title='Fleamarket Analytics')
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}
_cache = {'ts': 0.0, 'players': None, 'teams': None, 'events': None}

REFRESH_HOURS = 6


def refresh_data():
    """Pull fresh FPL data and regenerate the dashboard. Failures leave the
    previous files in place, so the app degrades to slightly-stale data."""
    try:
        for url, fn in [('https://fantasy.premierleague.com/api/bootstrap-static/', 'bootstrap.json'),
                        ('https://fantasy.premierleague.com/api/fixtures/', 'fixtures.json')]:
            req = urllib.request.Request(url, headers=UA)
            data = urllib.request.urlopen(req, timeout=25).read()
            json.loads(data)  # only overwrite with valid JSON
            with open(fn, 'wb') as f:
                f.write(data)
        subprocess.run([sys.executable, 'dashboard.py'], check=True, timeout=180)
        try:
            import momentum as mom
            boot = json.load(open('bootstrap.json', encoding='utf-8'))
            els = {e['id']: e for e in boot['elements']}
            teams = {t['id']: t['short_name'] for t in boot['teams']}
            n = mom.snapshot(els, teams)
            print(f'snapshot: {n} rows')
        except Exception as exc:  # noqa: BLE001
            print('snapshot skipped:', exc)
        print('data refresh ok')
    except Exception as exc:  # noqa: BLE001 - keep serving on any failure
        print(f'data refresh failed (serving previous data): {exc}')


def _refresh_forever():
    refresh_data()
    run_news_sweep()
    while True:
        time.sleep(REFRESH_HOURS * 3600)
        refresh_data()
        run_news_sweep()


@app.on_event('startup')
def _start_refresh():
    threading.Thread(target=_refresh_forever, daemon=True).start()


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
                      gwl=ns['HORIZON_EVENTS'],
                      elements={e['id']: e for e in boot['elements']})
    return _cache


POS_NAME = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}


def player_index(m):
    """[name, team, posName, price, fullname, sel%] for client-side search."""
    return sorted(([e['web_name'], m['teams'][e['team']], POS_NAME[e['element_type']],
                    e['now_cost'] / 10, f"{e['first_name']} {e['second_name']}",
                    float(e['selected_by_percent'])]
                   for e in m['elements'].values()), key=lambda r: -r[3])


def pick_best_xi(entries):
    """Choose a legal best XI (by 4-week total) from up to 15 entries.
    entries: dicts with 'pos' (1-4) and 'tt'. Returns set of indices."""
    if len(entries) <= 11:
        return set(range(len(entries)))
    order = sorted(range(len(entries)), key=lambda i: -entries[i]['tt'])
    min_req = {1: 1, 2: 3, 3: 2, 4: 1}
    max_all = {1: 1, 2: 5, 3: 5, 4: 3}
    xi = []
    for pos, need in min_req.items():
        xi += [i for i in order if entries[i]['pos'] == pos][:need]
    for i in order:
        if len(xi) >= 11:
            break
        if i in xi:
            continue
        if sum(1 for j in xi if entries[j]['pos'] == entries[i]['pos']) < max_all[entries[i]['pos']]:
            xi.append(i)
    return set(xi[:11])


def squad_table_html(entries, gwl, interactive=False):
    """Rich squad table: per-GW projections, totals, Starting XI footer.
    entries: dicts with n, t, pos, price, g (per-GW list), tt, xi, cap.
    interactive=True renders the role as an XI/C/VC/Bench selector with
    live-updating footer totals (captain doubled)."""
    head = ('<tr><th>Role</th><th>Player</th><th>Team</th><th>Pos</th><th class="num">£m</th>'
            + ''.join(f'<th class="num">GW{g}</th>' for g in gwl)
            + '<th class="num">Total</th></tr>')
    rows = ''
    ordered = sorted(entries, key=lambda r: (not r['xi'], r['pos']))
    bench_marked = False
    for r in ordered:
        bs = ''
        if not r['xi'] and not bench_marked:
            bench_marked, bs = True, ' class="benchstart"'
        low = r['xi'] and r['tt'] < 10
        if interactive:
            role = 'C' if (r.get('cap') and r['xi']) else ('XI' if r['xi'] else 'Bench')
            opts = ''.join(f"<option{' selected' if o == role else ''}>{o}</option>"
                           for o in ('XI', 'C', 'VC', 'Bench'))
            rawn = r.get('rawn', r['n'])
            role_cell = (f"<select class='role' data-i='{r.get('_i', '')}' data-g='{json.dumps(r['g'])}' "
                         f"style='background:var(--bg);color:var(--ink);border:1px solid var(--grid);"
                         f"border-radius:6px;padding:3px 6px;font:600 12px system-ui'>{opts}</select>"
                         f" <button type='button' class='subbtn' title='substitute this player' "
                         f"data-n=\"{rawn}\" data-t=\"{r['t']}\" data-p=\"{POS_NAME[r['pos']]}\" "
                         f"style='border:1px solid var(--grid);background:none;color:var(--ink2);"
                         f"border-radius:6px;padding:3px 7px;cursor:pointer;font-size:12px'>⇄</button>")
        else:
            role_cell = ('XI' if r['xi'] else 'bench') + (' (C)' if r.get('cap') else '')
        rows += (f"<tr{bs}><td style='white-space:nowrap'>{role_cell}</td><td><b>{r['n']}</b></td>"
                 f"<td>{r['t']}</td><td>{POS_NAME[r['pos']]}</td><td class='num'>{r['price']:.1f}</td>"
                 + ''.join(f"<td class='num'>{v:.1f}</td>" for v in r['g'])
                 + f"<td class='num {'low' if low else ''}'><b>{r['tt']:.1f}</b></td></tr>")
    xi = [r for r in entries if r['xi']]
    sums = [sum(r['g'][k] * (2 if r.get('cap') else 1) for r in xi) for k in range(len(gwl))]
    foot = ('<tr><th colspan="5" style="text-align:left">Starting XI (C doubled)'
            '<span id="xiwarn" style="color:var(--warn)"></span></th>'
            + ''.join(f"<th class='num' id='xf{k}'>{v:.1f}</th>" for k, v in enumerate(sums))
            + f"<th class='num' id='xft' style='color:var(--accent)'>{sum(sums):.1f}</th></tr>")
    script = ''
    if interactive:
        script = """<script>(function(){
 const sel=[...document.querySelectorAll('select.role')];
 function recompute(ev){
  if(ev){const t=ev.target;
   ['C','VC'].forEach(u=>{if(t.value===u)sel.forEach(s=>{if(s!==t&&s.value===u)s.value='XI'})});
  }
  const n=%d; const sums=Array(n).fill(0); let starters=0;
  sel.forEach(s=>{
   if(s.value==='Bench')return;
   starters++;
   const g=JSON.parse(s.dataset.g), m=s.value==='C'?2:1;
   g.forEach((v,k)=>sums[k]+=v*m);
  });
  sums.forEach((v,k)=>document.getElementById('xf'+k).textContent=v.toFixed(1));
  document.getElementById('xft').textContent=sums.reduce((a,b)=>a+b,0).toFixed(1);
  document.getElementById('xiwarn').textContent=starters===11?'':' — '+starters+' starters (need 11)';
 }
 sel.forEach(s=>s.addEventListener('change',recompute));
 recompute();
})()</script>""" % len(gwl)
    return (f'<div class="card"><div style="overflow-x:auto"><table>{head}{rows}{foot}</table></div>'
            f'{script}</div>')


PAGE = """<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:light dark;--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;
--muted:#898781;--grid:#e1e0d9;--ring:rgba(11,11,11,.10);--accent:#4a3aa7;--warn:#d03b3b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;
--ink2:#c3c2b7;--grid:#2c2c2a;--ring:rgba(255,255,255,.10);--accent:#9085e9;--warn:#e66767}}}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:0 20px 60px}}
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
tr.benchstart td{{border-top:2px solid var(--grid)}}
form{{display:flex;gap:8px;margin-top:8px}}
input{{flex:1;padding:9px 12px;border:1px solid var(--grid);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}}
button{{padding:9px 16px;border:none;border-radius:8px;background:var(--accent);color:#fff;font:600 14px system-ui;cursor:pointer}}
a{{color:var(--accent)}}
.note{{font-size:12.5px;color:var(--muted);margin-top:10px}}
.tabs{{display:flex;gap:2px;overflow-x:auto;border-bottom:1px solid var(--grid);margin:0 0 20px;scrollbar-width:none;position:sticky;top:0;background:var(--bg);z-index:6}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{padding:10px 13px;font:700 11.5px system-ui;letter-spacing:.09em;text-transform:uppercase;color:var(--ink2);text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap}}
.tab[aria-current]{{color:var(--ink);border-bottom-color:var(--accent)}}
.tab:hover{{color:var(--ink)}}
</style>
<div class="wrap">
<div class="eyebrow" style="padding:10px 0 2px">Fleamarket Analytics · 2026/27</div>
<nav class="tabs">
 <a class="tab" href="/#overview">Overview</a>
 <a class="tab" href="/#value">Value</a>
 <a class="tab" href="/#planner">Planner</a>
 <a class="tab" href="/#market">Market</a>
 <a class="tab" href="/#fixtures">Fixtures</a>
 <a class="tab" id="navnews" href="/news">News</a>
 <a class="tab" id="navsquads" href="/squads">Squads</a>
</nav>
<script>(function(){{
 var p=location.pathname;
 if(p.startsWith('/squads')||p.startsWith('/paste')||p.startsWith('/team')||p==='/me')
  document.getElementById('navsquads').setAttribute('aria-current','page');
 else if(p.startsWith('/news'))document.getElementById('navnews').setAttribute('aria-current','page');
}})()</script>
{body}
<p class="note"><a href="/">← Dashboard</a> · Scores are model xPts per match, averaged over the
next 4 gameweeks' fixtures, from prior-season Opta rates — a value lens, not an oracle.</p>
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


def best_transfers(owned, bank, m, top=3):
    """Best single transfers for a squad: same position, affordable with the
    bank, 3-per-club respected. owned = list of element dicts. Returns rows of
    (gain, out_el, out_xp, in_player)."""
    owned_ids = {e['id'] for e in owned}
    clubs = {}
    for e in owned:
        clubs[e['team']] = clubs.get(e['team'], 0) + 1
    out = []
    for el in owned:
        xp_out = m['players'].get(el['id'], {}).get('xpts', 0.0)
        budget = el['now_cost'] / 10 + bank
        best = None
        for cand in m['players'].values():
            if (cand['pos'] != el['element_type'] or cand['id'] in owned_ids
                    or cand['price'] > budget):
                continue
            incoming_club = clubs.get(cand['team'], 0) - (1 if cand['team'] == el['team'] else 0)
            if incoming_club >= 3:
                continue
            if best is None or cand['xpts'] > best['xpts']:
                best = cand
        if best and best['xpts'] - xp_out > 0.4:
            out.append((best['xpts'] - xp_out, el, xp_out, best))
    out.sort(key=lambda r: -r[0])
    return out[:top]


def transfers_html(owned, bank, m, bank_known=True, editable=False):
    rows = best_transfers(owned, bank, m)
    if not rows:
        return ''
    items = ''.join(
        f"<li><b>{el['web_name']}</b> ({xp_out:.2f}) → <b>{cand['name']}</b> "
        f"({m['teams'][cand['team']]}, £{cand['price']:.1f}, {cand['xpts']:.2f}) "
        f"<span style='color:var(--accent);font-weight:700'>+{gain:.2f} xPts</span>"
        + (f" <button type='button' class='apply' data-on=\"{el['web_name']}\" "
           f"data-ot=\"{m['teams'][el['team']]}\" data-inn=\"{cand['name']}\" "
           f"data-int=\"{m['teams'][cand['team']]}\" "
           f"style='margin-left:6px;background:var(--accent);color:#fff;border:none;"
           f"border-radius:6px;padding:3px 10px;font:600 12px system-ui;cursor:pointer'>Apply</button>"
           if editable else '') + '</li>'
        for gain, el, xp_out, cand in rows)
    note = '' if bank_known else ' Assumes £0.0 in the bank.'
    return ('<div class="card"><h2 style="font-size:16px">Best transfers by model</h2>'
            f'<p class="note" style="margin:2px 0 10px">Single swaps, same position, budget and '
            f'3-per-club respected.{note} Caveat: the model runs on last season’s rates — '
            'players in new bigger roles may be underrated.</p>'
            f"<ul style='padding-left:20px'>{items}</ul></div>")


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


PICKER = """<h1>Build your squad</h1>
<p class="sub">Search a player, click to add. Tap the ⓒ on a chip to set your captain.
Prefer typing? <a href="/paste?mode=text">Use the free-text version</a>.</p>
<div class="card">
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
 <button type="button" id="tmpl" style="background:none;border:1px solid var(--accent);color:var(--accent);border-radius:8px;padding:7px 13px;font:600 13px system-ui;cursor:pointer">⚡ Auto-fill the template</button>
 <button type="button" id="rand" style="background:none;border:1px solid var(--grid);color:var(--ink2);border-radius:8px;padding:7px 13px;font:600 13px system-ui;cursor:pointer">🎲 Random squad</button>
 <button type="button" id="resume" hidden style="background:none;border:1px solid var(--grid);color:var(--ink2);border-radius:8px;padding:7px 13px;font:600 13px system-ui;cursor:pointer">Load my last squad</button>
</div>
<input id="q" placeholder="Search players — e.g. Haal…" autocomplete="off"
 style="width:100%;padding:10px 12px;border:1px solid var(--grid);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit">
<div id="res" style="margin-top:8px;display:flex;flex-direction:column;gap:4px"></div>
<div id="chips" style="display:flex;flex-direction:column;gap:10px;margin-top:14px"></div>
<div style="margin-top:14px;display:flex;justify-content:space-between;align-items:center">
 <span id="count" class="note" style="margin:0">0 players · £0.0m used</span>
 <button id="go" disabled style="opacity:.5">Analyze</button>
</div></div>
<script>
const PIDX = __PIDX__;
const LIMITS = {GKP:2, DEF:5, MID:5, FWD:3};
const nrm = s => s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
const picked = [];
let tmplBaseline=null;
const q=document.getElementById('q'),res=document.getElementById('res'),
      chips=document.getElementById('chips'),go=document.getElementById('go'),
      count=document.getElementById('count');
let msgTimer=null;
function msg(t){
 count.innerHTML=`<b style="color:var(--warn)">${t}</b>`;
 clearTimeout(msgTimer); msgTimer=setTimeout(render,1800);
}
q.addEventListener('input',()=>{
 const v=nrm(q.value.trim()); res.innerHTML='';
 if(v.length<2)return;
 PIDX.filter(p=>nrm(p[0]).includes(v)||nrm(p[4]).includes(v)).slice(0,8).forEach(p=>{
  const b=document.createElement('button');
  b.type='button';
  b.style.cssText='text-align:left;background:none;border:1px solid var(--grid);color:var(--ink);border-radius:8px;padding:7px 11px;font:13.5px system-ui;cursor:pointer';
  b.innerHTML=`<b>${p[0]}</b> · ${p[1]} · ${p[2]} · £${p[3].toFixed(1)}`;
  b.onclick=()=>{
   if(picked.some(x=>x[0]===p[0]&&x[1]===p[1]))return;
   if(picked.length>=15){msg('Squad full (15 players)');return}
   if(picked.filter(x=>x[2]===p[2]).length>=LIMITS[p[2]]){msg(p[2]+' full (max '+LIMITS[p[2]]+')');return}
   if(picked.filter(x=>x[1]===p[1]).length>=3){msg('Max 3 players from '+p[1]);return}
   picked.push(p); q.value=''; res.innerHTML=''; render(); };
  res.appendChild(b);
 });
});
function render(){
 chips.innerHTML='';
 ['GKP','DEF','MID','FWD'].forEach(pos=>{
  const grp=picked.map((p,i)=>[p,i]).filter(([p])=>p[2]===pos);
  if(!grp.length)return;
  const row=document.createElement('div');
  row.style.cssText='display:flex;flex-wrap:wrap;gap:8px;align-items:center';
  const lab=document.createElement('span');
  lab.textContent=pos+' '+grp.length;
  lab.style.cssText='font:700 10px system-ui;letter-spacing:.08em;color:var(--ink2);min-width:44px';
  row.appendChild(lab);
  grp.forEach(([p,i])=>{
   const c=document.createElement('span');
   c.style.cssText='display:inline-flex;align-items:center;gap:7px;border:1px solid var(--grid);border-radius:99px;padding:5px 11px;font:600 13px system-ui;background:var(--surface)';
   c.innerHTML=`${p[0]} <span style="color:var(--ink2);font-weight:400">${p[1]} £${p[3].toFixed(1)}</span>`+
    `<button type="button" title="remove" style="border:none;background:none;color:var(--ink2);cursor:pointer;font-size:14px">✕</button>`;
   c.querySelector('button').onclick=()=>{picked.splice(i,1);render()};
   row.appendChild(c);
  });
  chips.appendChild(row);
 });
 const used=picked.reduce((s,p)=>s+p[3],0);
 const over=used>100;
 count.innerHTML=`<b>${picked.length}/15</b> players · <b style="${over?'color:var(--warn)':''}">£${used.toFixed(1)}m</b> used${over?' — over £100m!':''}`;
 const ready=picked.length===15;
 go.disabled=!ready; go.style.opacity=ready?'1':'.5';
 go.textContent=ready?'Analyze':'Analyze ('+picked.length+'/15)';
}

function autoTemplate(){
 picked.length=0;
 const need={GKP:2,DEF:5,MID:5,FWD:3};
 const minPos={}; PIDX.forEach(p=>{minPos[p[2]]=Math.min(minPos[p[2]]??99,p[3])});
 const cnt={GKP:0,DEF:0,MID:0,FWD:0}, club={};
 let used=0;
 for(const p of [...PIDX].sort((a,b)=>b[5]-a[5])){
  if(picked.length>=15)break;
  if(cnt[p[2]]>=need[p[2]])continue;
  if((club[p[1]]||0)>=3)continue;
  let minRest=0;
  for(const pos of ['GKP','DEF','MID','FWD'])
   minRest+=(need[pos]-cnt[pos]-(pos===p[2]?1:0))*minPos[pos];
  if(used+p[3]+minRest>100.0001)continue;
  picked.push(p);cnt[p[2]]++;club[p[1]]=(club[p[1]]||0)+1;used+=p[3];
 }
 tmplBaseline=picked.map(p=>`${p[0]} ${p[1]}`).join('\\n');
 render();
}
document.getElementById('tmpl').onclick=autoTemplate;

function randomSquad(){
 picked.length=0; tmplBaseline=null;
 const pool=PIDX.filter(p=>p[5]>=3);  // min 3% owned: no total blanks
 const need={GKP:2,DEF:5,MID:5,FWD:3};
 const minPos={}; pool.forEach(p=>{minPos[p[2]]=Math.min(minPos[p[2]]??99,p[3])});
 const cnt={GKP:0,DEF:0,MID:0,FWD:0}, club={};
 let used=0;
 for(const p of [...pool].sort(()=>Math.random()-0.5)){
  if(picked.length>=15)break;
  if(cnt[p[2]]>=need[p[2]])continue;
  if((club[p[1]]||0)>=3)continue;
  let minRest=0;
  for(const pos of ['GKP','DEF','MID','FWD'])
   minRest+=(need[pos]-cnt[pos]-(pos===p[2]?1:0))*minPos[pos];
  if(used+p[3]+minRest>100.0001)continue;
  picked.push(p);cnt[p[2]]++;club[p[1]]=(club[p[1]]||0)+1;used+=p[3];
 }
 render();
}
document.getElementById('rand').onclick=randomSquad;

const saved=localStorage.getItem('fpl_my_squad');
if(saved){
 const rb=document.getElementById('resume');
 rb.hidden=false;
 rb.onclick=()=>{
  picked.length=0;
  try{JSON.parse(saved).forEach(line=>{
   const parts=line.trim().split(' '), team=parts.pop(), name=parts.join(' ');
   const p=PIDX.find(x=>x[0]===name&&x[1]===team);
   if(p&&picked.length<15)picked.push(p);
  })}catch(e){}
  render();
 };
}
go.onclick=()=>{
 const lines=picked.map(p=>`${p[0]} ${p[1]}`);
 localStorage.setItem('fpl_my_squad', JSON.stringify(lines));
 const src=lines.join('\\n')===tmplBaseline?'&src=template':'';
 location='/paste?squad='+encodeURIComponent(lines.join('\\n'))+src;
};
</script>"""


@app.get('/paste', response_class=HTMLResponse)
def paste(squad: str = '', mode: str = '', src: str = '', name: str = '',
          type: str = '', sid: str = '', roles: str = '', gw: str = ''):
    if not squad.strip():
        if mode == 'text':
            return PAGE.format(title='Paste your squad', body=PASTE_FORM)
        m = model_data()
        pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        return PAGE.format(title='Build your squad',
                           body=PICKER.replace('__PIDX__', json.dumps(player_index(m), ensure_ascii=False)))
    m = model_data()
    pos_name = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    entries, problems, seen, owned = [], [], set(), []
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
        owned.append(el)
        mp = m['players'].get(el['id'])
        flag = ' ⚠ ' + el['news'][:36] if el['status'] not in ('a',) else ''
        entries.append({'n': el['web_name'] + flag, 'rawn': el['web_name'],
                        't': m['teams'][el['team']],
                        'pos': el['element_type'], 'price': el['now_cost'] / 10,
                        'g': mp['gws'] if mp else [0.0] * 4,
                        'tt': mp['tot4'] if mp else 0.0, 'cap': is_cap})
    locked = type in ('my', 'spy')
    if roles and len(roles) == len(entries):
        # real roles from the FPL import (X=XI, C=captain, V=vice, B=bench)
        for i, r in enumerate(entries):
            r['xi'] = roles[i] in 'XCV'
            r['cap'] = roles[i] == 'C'
    else:
        xi_idx = pick_best_xi(entries)
        for i, r in enumerate(entries):
            r['xi'] = i in xi_idx
    for i, r in enumerate(entries):
        r['_i'] = i
    table = squad_table_html(entries, m['gwl'], interactive=not locked) if entries else ''
    # legality check (catches the free-text path, which the picker pre-enforces)
    limits = {1: 2, 2: 5, 3: 5, 4: 3}
    for pos, cap_n in limits.items():
        n = sum(1 for r in entries if r['pos'] == pos)
        if n > cap_n:
            problems.append(f'<li>Illegal squad: {n}× {POS_NAME[pos]} (max {cap_n})</li>')
    clubs = {}
    for r in entries:
        clubs[r['t']] = clubs.get(r['t'], 0) + 1
    for club, n in clubs.items():
        if n > 3:
            problems.append(f'<li>Illegal squad: {n} players from {club} (max 3)</li>')
    prob_html = (f"<div class='card'><b>{len(problems)} issue(s)</b>"
                 f"<ul style='padding-left:20px;margin-top:6px'>{''.join(problems)}</ul></div>") if problems else ''
    icon = {'my': '⭐', 'spy': '🕵', 'tinker': '🔧'}.get(type, '')
    if name:
        title = f'{icon} {name}'.strip()
        kind = ('Your FPL team' if type == 'my' else 'Spied FPL team' if type == 'spy'
                else 'Tinker squad')
        intro = kind + (f' · synced GW{gw}' if gw else '')
        intro += (' · locked to the real thing — duplicate it to tinker. '
                  if locked else ' · roles and substitutions editable, totals update live. ')
    elif src == 'template':
        title = 'The template squad'
        intro = ('Built from the most-selected players in the game (a legal £100m squad of '
                 'the crowd’s favourites). The model then picked the best starting XI '
                 'among them — adjust any Role (XI / C / VC / Bench) and the totals update live. ')
    else:
        title = f'Squad analysis — {len(entries)} matched'
        intro = ('The model has picked the best legal starting XI — adjust any '
                 'Role (XI / C / VC / Bench) and the totals update live. ')
    lines_canon = [f"{r['rawn']} {r['t']}" for r in entries]
    if locked:
        edit_ui = """<p style="margin-top:14px"><button type="button" onclick="dupTinker()"
 style="background:var(--accent);color:#fff;border:none;border-radius:8px;padding:9px 16px;font:600 14px system-ui;cursor:pointer">🔧 Duplicate to tinker</button>
 <a href="/squads" style="margin-left:10px">← All squads</a></p>
<script>
const LINES=__LINES__, DNAME=__DNAME__, DROLES=__DROLES__;
function dupTinker(){
 let l=[];try{l=JSON.parse(localStorage.getItem('fpl_squads_v1'))||[]}catch(e){}
 const id='t'+Date.now();
 l.push({id:id,type:'tinker',name:DNAME+' (tinker)',lines:LINES,roles:DROLES,ts:Date.now()});
 localStorage.setItem('fpl_squads_v1',JSON.stringify(l));
 location='/paste?squad='+encodeURIComponent(LINES.join('\\n'))+'&name='+encodeURIComponent(DNAME+' (tinker)')+'&type=tinker&sid='+id+(DROLES?'&roles='+DROLES:'');
}
</script>"""
        edit_ui = (edit_ui.replace('__LINES__', json.dumps(lines_canon, ensure_ascii=False))
                          .replace('__DNAME__', json.dumps(name or 'Squad'))
                          .replace('__DROLES__', json.dumps(roles)))
        body = (f'<h1>{title}</h1><p class="sub">{intro}</p>'
                + table + prob_html
                + transfers_html(owned, 0.0, m, bank_known=False, editable=False)
                + edit_ui)
        return PAGE.format(title=name or 'Squad', body=body)

    edit_ui = """<div id="subpanel" hidden class="card">
<b id="sublabel"></b>
<input id="subq" placeholder="Search a replacement…" autocomplete="off"
 style="width:100%;margin-top:8px;padding:9px 12px;border:1px solid var(--grid);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit">
<div id="subres" style="margin-top:8px;display:flex;flex-direction:column;gap:4px"></div>
<p class="note" style="margin-top:8px"><button type="button" onclick="document.getElementById('subpanel').hidden=true"
 style="background:none;border:none;color:var(--ink2);cursor:pointer;text-decoration:underline;font:inherit">cancel</button></p>
</div>
<script>
const LINES=__LINES__, PIDX2=__PIDX2__, SID=__SID__, DNAME=__DNAME__;
const nrm2=s=>s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
function loadSquads(){try{return JSON.parse(localStorage.getItem('fpl_squads_v1'))||[]}catch(e){return[]}}
function currentRoles(){
 const arr=Array(LINES.length).fill('B');
 document.querySelectorAll('select.role').forEach(s=>{
  const i=+s.dataset.i;
  arr[i]={XI:'X',C:'C',VC:'V',Bench:'B'}[s.value]||'B';
 });
 return arr.join('');
}
function persist(lines,roles){
 if(!SID)return;
 const l=loadSquads(), e=l.find(x=>x.id===SID);
 if(e){e.lines=lines;e.roles=roles;e.ts=Date.now();localStorage.setItem('fpl_squads_v1',JSON.stringify(l));
  if(localStorage.getItem('fpl_primary')===SID)localStorage.setItem('fpl_my_squad',JSON.stringify(lines));}
}
function saveGo(lines){
 persist(lines,'');
 if(!SID)localStorage.setItem('fpl_my_squad', JSON.stringify(lines));
 location='/paste?squad='+encodeURIComponent(lines.join('\\n'))
  +(SID?'&sid='+SID+'&type=tinker&name='+encodeURIComponent(DNAME):'');
}
document.addEventListener('change',e=>{
 if(e.target.matches('select.role')&&SID)persist(LINES,currentRoles());
});
function saveAsNew(){
 const n=prompt('Name this squad:', DNAME||'My squad');
 if(!n)return;
 const l=loadSquads(), id='t'+Date.now();
 l.push({id:id,type:'tinker',name:n,lines:LINES,roles:currentRoles(),ts:Date.now()});
 localStorage.setItem('fpl_squads_v1',JSON.stringify(l));
 location='/paste?squad='+encodeURIComponent(LINES.join('\\n'))+'&name='+encodeURIComponent(n)+'&type=tinker&sid='+id+'&roles='+currentRoles();
}
function replaceLine(outN,outT,inN,inT){
 const lines=LINES.filter(l=>l!==outN+' '+outT);
 lines.push(inN+' '+inT);
 saveGo(lines);
}
let subTarget=null;
document.addEventListener('click',e=>{
 const a=e.target.closest('.apply');
 if(a){replaceLine(a.dataset.on,a.dataset.ot,a.dataset.inn,a.dataset.int);return}
 const s=e.target.closest('.subbtn');
 if(s){
  subTarget=[s.dataset.n,s.dataset.t,s.dataset.p];
  const panel=document.getElementById('subpanel');
  panel.hidden=false;
  document.getElementById('sublabel').textContent='Replace '+s.dataset.n+' ('+s.dataset.p+') with:';
  document.getElementById('subq').value='';
  document.getElementById('subres').innerHTML='';
  panel.scrollIntoView({behavior:'smooth',block:'center'});
  document.getElementById('subq').focus();
 }
});
document.getElementById('subq').addEventListener('input',()=>{
 if(!subTarget)return;
 const v=nrm2(document.getElementById('subq').value.trim());
 const res=document.getElementById('subres'); res.innerHTML='';
 if(v.length<2)return;
 const inSquad=new Set(LINES);
 const clubCount={};
 LINES.forEach(l=>{const t=l.trim().split(' ').pop(); clubCount[t]=(clubCount[t]||0)+1});
 PIDX2.filter(p=>p[2]===subTarget[2]&&!inSquad.has(p[0]+' '+p[1])
   &&(nrm2(p[0]).includes(v)||nrm2(p[4]).includes(v))).slice(0,8).forEach(p=>{
  const cc=(clubCount[p[1]]||0)-(p[1]===subTarget[1]?1:0);
  const b=document.createElement('button'); b.type='button';
  b.style.cssText='text-align:left;background:none;border:1px solid var(--grid);color:var(--ink);border-radius:8px;padding:7px 11px;font:13.5px system-ui;cursor:pointer';
  b.innerHTML=`<b>${p[0]}</b> · ${p[1]} · £${p[3].toFixed(1)}`+(cc>=3?` — max 3 from ${p[1]}`:'');
  if(cc>=3){b.disabled=true;b.style.opacity=.45}
  else b.onclick=()=>replaceLine(subTarget[0],subTarget[1],p[0],p[1]);
  res.appendChild(b);
 });
});
</script>"""
    edit_ui = (edit_ui.replace('__LINES__', json.dumps(lines_canon, ensure_ascii=False))
                      .replace('__PIDX2__', json.dumps(player_index(m), ensure_ascii=False))
                      .replace('__SID__', json.dumps(sid))
                      .replace('__DNAME__', json.dumps(name or 'My squad')))
    save_btn = ('' if sid else
                '<button type="button" onclick="saveAsNew()" style="background:var(--accent);color:#fff;'
                'border:none;border-radius:8px;padding:8px 14px;font:600 13px system-ui;cursor:pointer;'
                'margin-top:12px">💾 Save squad</button> ')
    body = (f'<h1>{title}</h1>'
            f'<p class="sub">{intro}'
            f'Use ⇄ on any row to substitute a player. <a href="/squads">← All squads</a></p>'
            + table + save_btn + prob_html
            + transfers_html(owned, 0.0, m, bank_known=False, editable=True)
            + edit_ui)
    return PAGE.format(title=name or 'Squad analysis', body=body)


REMEMBER_SNIPPET = """<p class="note"><button onclick="localStorage.setItem('fpl_team_id','{tid}');this.textContent='Remembered on this device ✓';this.disabled=true"
 style="background:none;border:1px solid var(--grid);color:var(--ink2);border-radius:8px;padding:6px 12px;font:600 12.5px system-ui;cursor:pointer">Remember as my team on this device</button></p>"""


@app.get('/', response_class=HTMLResponse)
def home():
    if os.path.exists('dashboard.html'):
        return HTMLResponse(open('dashboard.html', encoding='utf-8').read())
    return PAGE.format(title='Fleamarket Analytics', body=FORM)


NEWS_CACHE = 'news_cache.json'
_news_lock = threading.Lock()


def news_payload():
    try:
        return json.load(open(NEWS_CACHE, encoding='utf-8'))
    except Exception:
        return None


def run_news_sweep():
    """Background news sweep (~1 min). Skipped if the cache is fresh."""
    if not _news_lock.acquire(blocking=False):
        return
    try:
        import news as news_mod
        src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
        ns = {}
        exec(compile(src, 'model.py', 'exec'), ns)
        boot = json.load(open('bootstrap.json', encoding='utf-8'))
        els = {e['id']: e for e in boot['elements']}
        news_mod.sweep(ns['players'], els, ns['teams'], out=NEWS_CACHE)
        print('news sweep ok')
    except Exception as exc:  # noqa: BLE001
        print('news sweep failed:', exc)
    finally:
        _news_lock.release()


def news_is_stale(hours=4):
    p = news_payload()
    if not p:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(p['ts'])
        return age.total_seconds() > hours * 3600
    except Exception:
        return True


KIND_STYLE = {
    'reduce': ('#d03b3b', 'CUT MINUTES?'),
    'raise': ('#0ca30c', 'RAISE MINUTES?'),
    'watch': ('#fab219', 'WATCH'),
    'note': ('#898781', 'NOTE'),
}
TAG_LABEL = {'out': 'unavailable', 'doubt': 'fitness doubt', 'rotation': 'rotation',
             'return': 'return', 'lineup': 'team news', 'role': 'set pieces',
             'transfer': 'transfer'}


@app.get('/news', response_class=HTMLResponse)
def news_page(refresh: str = ''):
    import html as _h
    if refresh:
        threading.Thread(target=run_news_sweep, daemon=True).start()
        return PAGE.format(title='News', body=(
            '<h1>Sweeping…</h1><p class="sub">Fetching the latest headlines for the '
            'top-projected players — takes about a minute. '
            '<a href="/news">Reload the news page</a> shortly.</p>'))
    p = news_payload()
    if not p:
        if news_is_stale():
            threading.Thread(target=run_news_sweep, daemon=True).start()
        return PAGE.format(title='News', body=(
            '<h1>Player news</h1><p class="sub">First sweep is running — reload in a '
            'minute. <a href="/news">Reload</a></p>'))
    if news_is_stale():
        threading.Thread(target=run_news_sweep, daemon=True).start()

    props = ''
    order = {'reduce': 0, 'raise': 1, 'watch': 2, 'note': 3}
    for pr in sorted(p['proposals'], key=lambda x: order.get(x['kind'], 9)):
        colour, label = KIND_STYLE.get(pr['kind'], ('#898781', 'NOTE'))
        who, club = pr['player'].split('|')
        props += (
            f"<div style='border-left:3px solid {colour};padding:8px 0 8px 12px;margin-bottom:12px'>"
            f"<span style='color:{colour};font:700 10px system-ui;letter-spacing:.09em'>{label}</span> "
            f"<b>{_h.escape(who)}</b> <span style='color:var(--ink2)'>{_h.escape(club)}</span>"
            f"<div class='note' style='margin:2px 0 4px'>{_h.escape(pr['why'])}</div>"
            f"<div style='font-size:13.5px'>“{_h.escape(pr['headline'])}”</div>"
            f"<div class='note' style='margin-top:2px'>{_h.escape(pr['source'])} · {_h.escape(pr['when'])}"
            + (f" · <a href='{_h.escape(pr['url'])}' target='_blank' rel='noopener'>read</a>" if pr.get('url') else '')
            + "</div></div>")
    if not props:
        props = ('<p class="note">Nothing contradicts the model right now — no availability, '
                 'rotation or exit signals in the window.</p>')

    # market momentum, cross-referenced with the news
    momo = ''
    try:
        import momentum as mom
        m = model_data()
        src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
        ns = {}
        exec(compile(src, 'model.py', 'exec'), ns)
        mm = mom.momentum(ns['players'], m['elements'], m['teams'])
        if mm['quiet']:
            momo = ('<p class="note">No transfer movement yet — net transfers start flowing '
                    'once the gameweek opens, and ownership deltas need a few hours of '
                    f'baseline (currently {mm["span_h"]:.0f}h collected).</p>')
        else:
            rows = mom.correlate(mm, p)
            head = ('<tr><th>Player</th><th class="num">£m</th><th class="num">Own%</th>'
                    + ('<th class="num">Net in</th>' if mm['live'] else '<th class="num">Own Δ</th>')
                    + '<th class="num">model xPts</th><th>Catalyst</th></tr>')
            body = ''
            for r in rows:
                who, club = r['player'].split('|')
                move = (f"{r['net']:+,}" if mm['live'] else
                        (f"{r['d_sel']:+.1f}pp" if r['d_sel'] is not None else '–'))
                cat = (f"<span style='color:var(--ink2)'>“{_h.escape(r['headline'][:70])}” "
                       f"— {_h.escape(r['source'])}</span>" if r['explained'] else
                       "<b style='color:#fab219'>no story found</b>")
                body += (f"<tr><td><b>{_h.escape(who)}</b> <span style='color:var(--muted)'>"
                         f"{_h.escape(club)}</span></td><td class='num'>{r['price']:.1f}</td>"
                         f"<td class='num'>{r['sel']:.1f}</td><td class='num'>{move}</td>"
                         f"<td class='num'>{r['xpts']:.2f}</td><td style='white-space:normal'>{cat}</td></tr>")
            momo = (f"<div style='overflow-x:auto'><table>{head}{body}</table></div>"
                    "<p class='note' style='margin-top:8px'>“No story found” is the interesting "
                    "column: the crowd is moving without a public catalyst — either they know "
                    "something, or it is a bandwagon feeding itself.</p>")
    except Exception as exc:  # noqa: BLE001
        momo = f'<p class="note">Momentum unavailable ({_h.escape(str(exc)[:80])}).</p>'

    disc = ''
    for r in p.get('discoveries', []):
        who, club = r['player'].split('|')
        chips = ''.join(
            f"<span style='border:1px solid var(--grid);border-radius:99px;padding:1px 8px;"
            f"font:600 10.5px system-ui;color:var(--ink2);margin-left:6px'>{TAG_LABEL.get(t, t)}</span>"
            for t in r['tags'])
        lis = ''.join(
            f"<li style='margin-bottom:4px'>{_h.escape(i['title'])}"
            f"<span class='note'> — {_h.escape(i['source'])}"
            + (f" · <a href='{_h.escape(i['url'])}' target='_blank' rel='noopener'>read</a>" if i.get('url') else '')
            + "</span></li>" for i in r['items'][:2])
        disc += (
            f"<div style='border-top:1px solid var(--grid);padding:11px 0'>"
            f"<b>{_h.escape(who)}</b> <span style='color:var(--ink2);font-size:13px'>{_h.escape(club)} · "
            f"£{r['price']:.1f} · {r['sel']:.1f}% owned · model {r['xpts']:.2f} xPts / {r['xmins']} mins</span>{chips}"
            f"<div class='note' style='margin:3px 0 2px'>{_h.escape(r['why'])}</div>"
            f"<ul style='padding-left:20px;margin:4px 0 0;font-size:13.5px'>{lis}</ul></div>")
    if not disc:
        disc = '<p class="note">Nothing off-radar surfaced in this window.</p>'

    feed = ''
    for key, items in p['players'].items():
        who, club = key.split('|')
        tags = sorted({t for i in items for t in i['tags']})
        chips = ''.join(
            f"<span style='border:1px solid var(--grid);border-radius:99px;padding:1px 8px;"
            f"font:600 10.5px system-ui;color:var(--ink2);margin-left:6px'>{TAG_LABEL.get(t, t)}</span>"
            for t in tags)
        lis = ''.join(
            f"<li style='margin-bottom:5px'>{_h.escape(i['title'])}"
            f"<span class='note'> — {_h.escape(i['source'])} · {_h.escape(i['when'])}"
            + (f" · <a href='{_h.escape(i['url'])}' target='_blank' rel='noopener'>read</a>" if i.get('url') else '')
            + "</span></li>" for i in items[:4])
        feed += (f"<div style='border-top:1px solid var(--grid);padding:12px 0'>"
                 f"<b>{_h.escape(who)}</b> <span style='color:var(--ink2);font-size:13px'>{_h.escape(club)}</span>{chips}"
                 f"<ul style='padding-left:20px;margin-top:6px;font-size:13.5px'>{lis}</ul></div>")
    if not feed:
        feed = '<p class="note">No player headlines in the window.</p>'

    when = p['ts'].replace('T', ' ')[:16]
    body = (
        '<h1>Player news</h1>'
        f'<p class="sub">Headlines from the last {p["days"]} days for the '
        f'{p["swept"]} highest-projected players plus every curated minutes override, '
        'classified and cross-checked against the model. Suggestions only — nothing here '
        'edits the model.</p>'
        f'<div class="card"><h2 style="font-size:16px">Flagged against the model</h2>'
        f'<p class="note">Where the news disagrees with our expected-minutes assumption.</p>'
        f'{props}</div>'
        f'<div class="card"><h2 style="font-size:16px">Market momentum</h2>'
        f'<p class="note">Who the crowd is buying, matched against the headlines.</p>'
        f'{momo}</div>'
        f'<div class="card"><h2 style="font-size:16px">Off the radar</h2>'
        f'<p class="note">Found the other way round — reading all 20 clubs\' team-news feeds and '
        f'matching any player, then keeping the ones our model does <i>not</i> rate. Ranked by how '
        f'much they should change our view.</p>{disc}</div>'
        f'<div class="card"><h2 style="font-size:16px">Everything we found</h2>{feed}</div>'
        f'<p class="note">Swept {when} UTC · re-sweeps every few hours · '
        f'<a href="/news?refresh=1">↻ sweep now</a></p>')
    return PAGE.format(title='Player news', body=body)


@app.get('/api/team/{team_id}')
def api_team(team_id: int, request: Request):
    """Latest LOCKED gameweek picks for any FPL team, as squad lines + roles.
    Used by the Squads page to auto-sync ⭐/🕵 squads after each deadline."""
    m = model_data()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    locked = [e['id'] for e in m['events'] if e['deadline_time'] <= now]
    try:
        entry = fpl_get(f'https://fantasy.premierleague.com/api/entry/{team_id}/')
    except Exception:
        return {'error': 'team not found'}
    name = entry.get('name', f'Team {team_id}')
    if not locked:
        # localhost-only pre-deadline preview: serve the user's entered team
        # from my_team_preview.json; real locked picks supersede it after GW1
        if (request.client and request.client.host in ('127.0.0.1', '::1')
                and os.path.exists('my_team_preview.json')):
            pv = json.load(open('my_team_preview.json', encoding='utf-8'))
            if pv.get('team_id') == team_id:
                return {'name': name, 'gw': 1, 'simulated': True,
                        'lines': pv['lines'], 'roles': pv['roles']}
        return {'name': name, 'gw': None, 'error': 'no locked gameweek yet'}
    gw = max(locked)
    try:
        picks = fpl_get(f'https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/')
        assert 'picks' in picks
    except Exception:
        return {'name': name, 'gw': None, 'error': f'no picks for GW{gw}'}
    lines, roles = [], ''
    for pk in picks['picks']:
        el = m['elements'].get(pk['element'])
        if not el:
            continue
        lines.append(f"{el['web_name']} {m['teams'][el['team']]}")
        roles += ('C' if pk['is_captain'] else 'V' if pk['is_vice_captain']
                  else 'X' if pk['position'] <= 11 else 'B')
    return {'name': name, 'gw': gw, 'lines': lines, 'roles': roles}


SQUADS_PAGE = """<h1>Squads</h1>
<p class="sub">⭐ your FPL team and 🕵 spied rivals sync themselves after every deadline;
🔧 tinker squads are yours to edit. The ★ primary squad drives the dashboard markers.</p>
<div class="card">
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
 <a href="/paste" style="text-decoration:none;background:var(--accent);color:#fff;border-radius:8px;padding:8px 14px;font:600 13px system-ui">+ Build new</a>
 <button type="button" id="importmy" style="background:none;border:1px solid var(--accent);color:var(--accent);border-radius:8px;padding:8px 14px;font:600 13px system-ui;cursor:pointer">⭐ Import my team</button>
 <button type="button" id="addspy" style="background:none;border:1px solid var(--grid);color:var(--ink2);border-radius:8px;padding:8px 14px;font:600 13px system-ui;cursor:pointer">🕵 Add spy</button>
 <button type="button" id="refresh" style="background:none;border:1px solid var(--grid);color:var(--ink2);border-radius:8px;padding:8px 14px;font:600 13px system-ui;cursor:pointer">↻ Refresh teams</button>
</div>
<div id="cards" style="display:flex;flex-direction:column;gap:10px"><p class="note">Loading…</p></div>
</div>
<script>
const ICON={my:'⭐',spy:'🕵',tinker:'🔧'};
const load=()=>{try{return JSON.parse(localStorage.getItem('fpl_squads_v1'))||[]}catch(e){return[]}};
const save=l=>localStorage.setItem('fpl_squads_v1',JSON.stringify(l));
function migrate(){
 let l=load();
 if(!l.length){
  const old=localStorage.getItem('fpl_my_squad');
  if(old){try{l.push({id:'t'+Date.now(),type:'tinker',name:'My draft',lines:JSON.parse(old),ts:Date.now()})}catch(e){}}
 }
 const tid=localStorage.getItem('fpl_team_id');
 if(tid&&!l.some(s=>s.type==='my'))l.unshift({id:'my',type:'my',name:'My FPL team',teamId:tid,lines:[],roles:'',lastGw:0});
 save(l);return l;
}
function primary(){return localStorage.getItem('fpl_primary')}
function setPrimary(s){
 localStorage.setItem('fpl_primary',s.id);
 if(s.lines&&s.lines.length)localStorage.setItem('fpl_my_squad',JSON.stringify(s.lines));
 render();
}
function detailUrl(s){
 if(!s.lines||!s.lines.length)return null;
 return '/paste?squad='+encodeURIComponent(s.lines.join('\\n'))+'&name='+encodeURIComponent(s.name)
  +'&type='+s.type+'&sid='+s.id+(s.roles?'&roles='+s.roles:'')+(s.lastGw?'&gw='+s.lastGw:'');
}
function render(){
 const l=load(), box=document.getElementById('cards');
 if(!l.length){box.innerHTML='<p class="note">No squads yet — build one, import your FPL team, or add a spy.</p>';return}
 const ord={my:0,spy:1,tinker:2};
 l.sort((a,b)=>ord[a.type]-ord[b.type]||(b.ts||0)-(a.ts||0));
 box.innerHTML='';
 l.forEach(s=>{
  const url=detailUrl(s);
  const c=document.createElement('div');
  c.style.cssText='display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;border:1px solid var(--grid);border-radius:10px;padding:12px 14px';
  const meta=s.type==='tinker'?'tinker squad':(s.sim?'preview of your entered team (pre-deadline)':(s.lastGw?'synced GW'+s.lastGw+(s.updated?' · <b style=\\'color:var(--accent)\\'>updated</b>':''):(s.lines&&s.lines.length?'synced':'awaiting first sync — reload or press ↻ Refresh teams; fills after the next deadline')));
  c.innerHTML=`<div><div style="font:700 15px system-ui">${ICON[s.type]} ${s.name} ${primary()===s.id?'<span title="primary — drives dashboard markers" style="color:var(--accent)">★</span>':''}</div>
   <div class="note" style="margin:2px 0 0">${meta}${s.lines&&s.lines.length?' · '+s.lines.length+' players':''}</div></div>
   <div style="display:flex;gap:6px;flex-wrap:wrap"></div>`;
  const btns=c.lastElementChild;
  const mk=(txt,fn,title)=>{const b=document.createElement('button');b.textContent=txt;b.title=title||'';
   b.style.cssText='background:none;border:1px solid var(--grid);color:var(--ink2);border-radius:7px;padding:5px 10px;font:600 12px system-ui;cursor:pointer';
   b.onclick=fn;btns.appendChild(b)};
  if(url)mk('Open',()=>location=url);
  if(primary()!==s.id&&s.lines&&s.lines.length)mk('★',()=>setPrimary(s),'set as primary');
  mk('Duplicate',()=>{const l2=load();const cp={id:'t'+Date.now(),type:'tinker',name:s.name+' (tinker)',lines:[...(s.lines||[])],roles:s.roles||'',ts:Date.now()};l2.push(cp);save(l2);render()},'copy to an editable tinker squad');
  if(s.type==='tinker'){
   mk('Rename',()=>{const n=prompt('Squad name:',s.name);if(n){const l2=load();l2.find(x=>x.id===s.id).name=n;save(l2);render()}});
  }
  if(s.type!=='my')mk('Delete',()=>{if(confirm('Delete "'+s.name+'"?')){const l2=load();save(l2.filter(x=>x.id!==s.id));render()}});
  box.appendChild(c);
 });
}
async function sync(force){
 const l=load();let any=false;
 for(const s of l){
  if(s.type!=='my'&&s.type!=='spy')continue;
  const tid=(s.teamId||'').toString().replace(/\\D/g,'');  // digits only — self-heals bad input
  if(!tid)continue;
  s.teamId=tid;
  try{
   const r=await fetch('/api/team/'+tid).then(x=>x.json());
   if(r.name)s.name=r.name;
   if(r.gw&&(force||r.gw>(s.lastGw||0))){
    s.lines=r.lines;s.roles=r.roles;s.updated=true;any=true;
    s.sim=!!r.simulated;
    s.lastGw=r.simulated?0:r.gw;  // simulated preview: real GW1 will supersede
   } else if(!r.simulated) s.updated=false;
  }catch(e){}
 }
 save(l);
 const p=l.find(x=>x.id===primary());
 if(p&&p.lines&&p.lines.length)localStorage.setItem('fpl_my_squad',JSON.stringify(p.lines));
 render();
}
document.getElementById('refresh').onclick=()=>sync(true);
document.getElementById('importmy').onclick=()=>{
 let tid=prompt('Your FPL team ID (from the Points page URL):',localStorage.getItem('fpl_team_id')||'');
 if(!tid)return;
 tid=tid.replace(/\\D/g,'');
 if(!tid){alert('That doesn\\u2019t look like a team ID — digits only.');return}
 localStorage.setItem('fpl_team_id',tid);
 const l=load();let mine=l.find(s=>s.type==='my');
 if(mine)mine.teamId=tid;else l.unshift({id:'my',type:'my',name:'My FPL team',teamId:tid,lines:[],roles:'',lastGw:0});
 if(!primary())localStorage.setItem('fpl_primary','my');
 save(l);sync(true);
};
document.getElementById('addspy').onclick=()=>{
 let tid=prompt('Rival FPL team ID to track:');
 if(!tid)return;
 tid=tid.replace(/\\D/g,'');
 if(!tid){alert('That doesn\\u2019t look like a team ID — digits only.');return}
 const l=load();l.push({id:'s'+Date.now(),type:'spy',name:'Team '+tid,teamId:tid,lines:[],roles:'',lastGw:0});
 save(l);sync(true);
};
migrate();render();sync(false);
</script>"""


@app.get('/squads', response_class=HTMLResponse)
def squads():
    return PAGE.format(title='Squads', body=SQUADS_PAGE)


@app.get('/me', response_class=HTMLResponse)
def me(request: Request):
    """Personal dashboard (includes the squad) — localhost only, by design."""
    if request.client and request.client.host in ('127.0.0.1', '::1') \
            and os.path.exists('my_dashboard.html'):
        return HTMLResponse(open('my_dashboard.html', encoding='utf-8').read())
    return PAGE.format(title='Not available',
                       body='<h1>Not available here</h1><p class="sub">The personal '
                            'dashboard is only served on localhost.</p>')


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
                'or <a href="/paste">build your squad manually</a> to analyze it now.</p></div>'
                + REMEMBER_SNIPPET.format(tid=team_id))
        return PAGE.format(title=name, body=body)

    entries, owned = [], []
    for pk in picks['picks']:
        el = m['elements'].get(pk['element'])
        mp = m['players'].get(pk['element'])
        owned.append(el)
        entries.append({'n': el['web_name'], 't': m['teams'][el['team']],
                        'pos': el['element_type'], 'price': el['now_cost'] / 10,
                        'g': mp['gws'] if mp else [0.0] * 4,
                        'tt': mp['tot4'] if mp else 0.0,
                        'xi': pk['position'] <= 11, 'cap': pk['is_captain']})
    table = squad_table_html(entries, m['gwl'])
    xi_total = sum(r['tt'] * (2 if r['cap'] else 1) for r in entries if r['xi'])

    bank = (picks.get('entry_history') or {}).get('bank')
    sugg = transfers_html(owned, (bank / 10) if bank is not None else 0.0, m,
                          bank_known=bank is not None)

    body = (f'<h1>{name}</h1><p class="sub">{manager} · GW{gw} squad · projected '
            f'<b>{xi_total:.1f}</b> XI points over the next 4 GWs (captain doubled)</p>'
            + table + sugg
            + REMEMBER_SNIPPET.format(tid=team_id))
    return PAGE.format(title=name, body=body)
