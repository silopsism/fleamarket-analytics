"""Generate dashboard.html: self-contained FPL model dashboard.

Reuses model.py's scoring (exec'd up to the SCORES-END marker), inlines the
data as JSON, and writes a single static HTML file — servable from any
static host (home server, python -m http.server, nginx).
"""
import json
from collections import defaultdict

src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
ns = {}
exec(compile(src, 'model.py', 'exec'), ns)
players, teams = ns['players'], ns['teams']
pos_name = ns['pos_name']

V4_XI = [('Kinsky', 'TOT'), ('Guéhi', 'MCI'), ('Mosquera', 'ARS'),
         ('Maguire', 'MUN'), ('B.Fernandes', 'MUN'), ('Szoboszlai', 'LIV'),
         ('Mbeumo', 'MUN'), ('E.Le Fée', 'SUN'), ('Haaland', 'MCI'),
         ('João Pedro', 'CHE'), ('Calvert-Lewin', 'LEE')]
V4_BENCH = [('Verbruggen', 'BHA'), ('Davis', 'IPS'), ('van Ewijk', 'COV'),
            ('Hughes', 'CRY')]
V4 = set(V4_XI) | set(V4_BENCH)


def pkey(p):
    return (p['name'], teams[p['team']])


# embed ALL players so saved squads always resolve fully; the charts filter
# to >=1.8 xPts at draw time to stay readable
pts = players
_els_by_id = {e['id']: e for e in ns['d']['elements']}


def _price_move(pid):
    """FPL's own price-change signal: current progress and tonight's odds."""
    e = _els_by_id.get(pid) or {}
    try:
        pct = float(e.get('price_change_percent') or 0)
    except (TypeError, ValueError):
        pct = 0.0
    lik = 0.0
    for pr in (e.get('price_change_projections') or [])[:1]:
        try:
            lik = float(pr.get('likelihood') or 0)
        except (TypeError, ValueError):
            lik = 0.0
    return round(pct, 1), round(lik, 2)


data = []
for p in pts:
    pct, lik = _price_move(p['id'])
    data.append({'n': p['name'], 't': teams[p['team']], 'p': pos_name[p['pos']],
                 'c': p['price'], 'x': round(p['xpts'], 2), 'xn': round(p['xnext'], 2),
                 'g': p['gws'], 'tt': p['tot4'], 'pc': pct, 'pl': lik,
                 's': p['sel'], 'v4': pkey(p) in V4, 'xi': pkey(p) in set(V4_XI)})
gw_labels = ns['HORIZON_EVENTS']

fx = json.load(open('fixtures.json', encoding='utf-8'))
runs = defaultdict(dict)
for f in fx:
    if f['event'] and f['event'] <= 6:
        runs[teams[f['team_h']]][f['event']] = {'o': teams[f['team_a']], 'd': f['team_h_difficulty'], 'h': 1}
        runs[teams[f['team_a']]][f['event']] = {'o': teams[f['team_h']], 'd': f['team_a_difficulty'], 'h': 0}
order = sorted(runs, key=lambda t: sum(g['d'] for g in runs[t].values()))
heat = [{'team': t, 'gws': [runs[t].get(gw) for gw in range(1, 7)]} for t in order]

squad_rows = []
for name, club in V4_XI + V4_BENCH:
    p = next(q for q in players if q['name'] == name and teams[q['team']] == club)
    squad_rows.append({'n': name, 't': club, 'p': pos_name[p['pos']],
                       'c': p['price'], 'g': p['gws'], 'tt': p['tot4'],
                       'xi': (name, club) in set(V4_XI)})

html = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fleamarket Analytics</title>
<style>
:root{color-scheme:light;
 --bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--accent:#4a3aa7;
 --def:#2a78d6;--mid:#eb6834;--fwd:#1baf7a;--gkp:#898781;
 --h2:#cde2fb;--h3:#86b6ef;--h4:#3987e5;--h5:#104281;--hd2:#0b0b0b;--hd4:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--accent:#9085e9;
 --def:#3987e5;--mid:#d95926;--fwd:#199e70;--gkp:#898781}}
:root[data-theme="dark"]{color-scheme:dark;
 --bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--accent:#9085e9;
 --def:#3987e5;--mid:#d95926;--fwd:#199e70;--gkp:#898781}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:0 20px 60px}
.wrap{max-width:980px;margin:0 auto}
header{margin-bottom:28px}
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:clamp(26px,4.5vw,38px);letter-spacing:-.02em;text-wrap:balance}
.sub{color:var(--ink2);max-width:62ch;margin-top:6px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:20px;margin-top:22px}
h2{font-size:16px;margin-bottom:2px}
.note{font-size:12.5px;color:var(--muted);margin-bottom:14px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.chip{border:1px solid var(--ring);background:none;color:var(--ink2);font:600 12px system-ui;padding:5px 11px;border-radius:99px;cursor:pointer;display:flex;align-items:center;gap:6px}
.chip[aria-pressed="true"]{background:color-mix(in srgb, var(--accent) 18%, var(--surface));border-color:var(--accent);color:var(--ink);font-weight:700}
.chip .sw{width:10px;height:10px;border-radius:3px}
.chip[data-p="GKP"] .sw{border-radius:1px}
#scat{width:100%;height:auto;display:block}
.tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--axis);border-radius:8px;padding:8px 11px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.18);opacity:0;transition:opacity .12s;z-index:9;max-width:230px}
.tip b{font-size:13.5px}
.tip .r{color:var(--ink2)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);text-align:left;padding:6px 10px;border-bottom:1px solid var(--grid)}
td{padding:6px 10px;border-bottom:1px solid var(--grid);font-size:13.5px;white-space:nowrap}
td.num,th.num{text-align:right}
.hm td{padding:3px}
.cell{min-width:52px;text-align:center;border-radius:5px;font:600 11.5px system-ui;padding:5px 4px}
.d2{background:var(--h2);color:#0b0b0b}.d3{background:var(--h3);color:#0b0b0b}
.d4{background:var(--h4);color:#fff}.d5{background:var(--h5);color:#fff}
.teamlab{font-weight:700;font-size:12.5px;padding-right:10px}
.pill{display:inline-block;font:700 10px system-ui;letter-spacing:.06em;border:1px solid var(--ring);border-radius:99px;padding:2px 8px;color:var(--ink2)}
.xi .pill{color:var(--accent);border-color:var(--accent)}
footer{margin-top:26px;font-size:12px;color:var(--muted);max-width:70ch}
.tabs{display:flex;gap:2px;overflow-x:auto;border-bottom:1px solid var(--grid);margin:0 0 4px;scrollbar-width:none;position:sticky;top:0;background:var(--bg);z-index:6}
.tabs::-webkit-scrollbar{display:none}
.tab{padding:10px 13px;font:700 11.5px system-ui;letter-spacing:.09em;text-transform:uppercase;color:var(--ink2);text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap}
.tab[aria-current]{color:var(--ink);border-bottom-color:var(--accent)}
.tab:hover{color:var(--ink)}
.tabpane{display:none}
.tabpane.active{display:block}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px}
.tile .tl{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:700}
.tile .tv{font-size:21px;font-weight:700;letter-spacing:-.01em;margin-top:5px}
.tile .ts{font-size:12px;color:var(--ink2);margin-top:2px}
.selcol{background:color-mix(in srgb, var(--accent) 9%, transparent)}
.absent{opacity:.35}
tr.benchstart td{border-top:2px solid var(--axis)}
.mvup{color:#0ca30c;font-weight:700}
.mvdn{color:#d03b3b;font-weight:700}
th.gwsel{cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}
th.gwsel:hover{color:var(--ink)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:16px;align-items:start}
.cols3{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:22px;margin-top:14px;align-items:start}
.mini{font-size:13.5px;line-height:1.45}
.mini .row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--grid)}
.mini .row:last-child{border-bottom:0}
.mini b{font-weight:700}
.up{color:#0ca30c;font-weight:700}
.down{color:#d03b3b;font-weight:700}
.stack{display:flex;flex-direction:column;gap:24px}
@media(max-width:700px){.cols{grid-template-columns:1fr}}
h3{font-size:13.5px;margin-bottom:8px}
.mut{font-size:11px;color:var(--muted);font-weight:400;letter-spacing:.04em;text-transform:uppercase}
#diff{width:100%;height:auto;display:block}
</style>
<div class="wrap">
<div class="eyebrow" style="padding:10px 0 2px">Fleamarket Analytics · 2026/27</div>
<nav class="tabs">
 <a class="tab" href="#overview">Overview</a>
 <a class="tab" href="#value">Value</a>
 <a class="tab" href="#planner">Planner</a>
 <a class="tab" href="#market">Market</a>
 <a class="tab" href="#fixtures">Fixtures</a>
 <a class="tab" href="/news">News ↗</a>
 <a class="tab" href="/squads">Squads ↗</a>
</nav>

<div class="tabpane" data-tab="overview">
<p class="sub" style="margin-top:16px">Every player scored from last season's Opta rates (xG, xA,
clean sheets, defensive contributions), season expectations, and fixtures. __SUBNOTE__</p>
<div class="tiles">
 <div class="tile"><div class="tl">Next deadline</div><div class="tv">__DL_TIME__</div><div class="ts">__DL_GW__</div></div>
 <div class="tile"><div class="tl">Top value</div><div class="tv">__TV_NAME__</div><div class="ts">__TV_SUB__</div></div>
 <div class="tile"><div class="tl">Top differential</div><div class="tv">__TD_NAME__</div><div class="ts">__TD_SUB__</div></div>
 <div class="tile"><div class="tl">Model top scorer</div><div class="tv">__TS_NAME__</div><div class="ts">__TS_SUB__</div></div>
 <div class="tile" id="tile-squad" hidden><div class="tl">Your XI, next 4 GWs</div><div class="tv" id="tile-squad-v">–</div><div class="ts">model projection</div></div>
 <div class="tile"><div class="tl">Model optimum, 4 GWs</div><div class="tv">__OPTTOTAL__</div><div class="ts">best legal plan · <a href="/squads">open in Squads</a></div></div>
</div>

<section class="card" id="mysec" hidden>
 <h2>Your squad — what needs attention</h2>
 <p class="note" id="mysecnote"></p>
 <div class="cols3">
  <div><h3>Captain this week</h3><div id="capbox"></div></div>
  <div><h3>Best transfers</h3><div id="trbox"></div></div>
  <div><h3>Price watch</h3><div id="pwbox"></div></div>
 </div>
</section>

<section class="card" id="nosquadsec">
 <h2>Track your squad here</h2>
 <p class="note" style="margin-bottom:0">Import your FPL team or build one in
 <a href="/squads">Squads</a> and this page gains a captain pick, transfer suggestions and a
 price watch for your own players.</p>
</section>

<section class="card">
 <h2>Market movements <span class="mut">__MOVEWIN__</span></h2>
 <p class="note">Who the crowd is buying and selling right now, from our own snapshot history.
 Full detail and news cross-checks on the <a href="/news">News</a> tab.</p>
 <div class="cols" id="movecols">__MOVES__</div>
</section>

<section class="card">
 <h2>Top stories</h2>
 <p class="note">Highest-signal headlines from the last few days, checked against the model's
 assumptions. All of them, plus off-radar finds, on the <a href="/news">News</a> tab.</p>
 __STORIES__
</section>
__SQUADSEC__
</div>

<div class="tabpane" data-tab="value">
__VALUEBANDS__
</div>

<div class="tabpane" data-tab="planner">
<section class="card">
 <h2>Next 4 gameweeks — the planner</h2>
 <p class="note">Projected points per gameweek against each team's actual fixtures, plus the 4-week total.
 Top 5 keepers, 15 defenders, 20 midfielders, 10 forwards by the selected metric. __RINGNOTE__</p>
 <div class="chips" id="plannerchips"></div>
 <div class="scroll"><table id="planner"></table></div>
</section>
</div>

<div class="tabpane" data-tab="market">
<section class="card">
 <h2>Differentials &amp; traps — the model vs the crowd</h2>
 <p class="note">Ownership against model score. Top-left: gems the crowd hasn't found. Bottom-right: popular picks the model doubts. Ownership axis is stretched at the low end.</p>
 <div class="chips" id="chips2"></div>
 <svg id="diff" viewBox="0 0 940 440" role="img" aria-label="Scatter of ownership against expected points per match"></svg>
 <div class="cols">
  <div><h3>Top differentials <span class="mut">under 10% owned</span></h3>
  <div class="scroll"><table><tr><th>Player</th><th>Team</th><th class="num">£m</th><th class="num">Own%</th><th class="num">xPts</th></tr>__DIFFROWS__</table></div></div>
  <div><h3>Crowd traps <span class="mut">15%+ owned, model skeptical</span></h3>
  <div class="scroll"><table><tr><th>Player</th><th>Team</th><th class="num">£m</th><th class="num">Own%</th><th class="num">xPts</th></tr>__TRAPROWS__</table></div>
  <p class="note" style="margin:8px 0 0">Model uses last season's rates — players in new, bigger roles this season may be unfairly flagged.</p></div>
 </div>
</section>
</div>

<div class="tabpane" data-tab="fixtures">
<section class="card">
 <h2>Opening fixtures — GW1–6</h2>
 <p class="note">Sorted easiest run first. Darker = harder (FPL difficulty rating). Uppercase = home.</p>
 <div class="scroll hm"><table id="heatmap"></table></div>
</section>
</div>

<footer>Phase 1 model: built on prior-season Opta rates, expected minutes, transfer
context, season expectations and fixtures — a value lens, not an oracle.
<br>FPL data pulled __PULLED__ UK · refreshes automatically every 6 hours.</footer>
</div>
<div class="tip" id="tip"></div>
<script>
const DATA = __DATA__;
const HEAT = __HEAT__;
const SQUAD = __SQUAD__;
const GWL = __GWL__;
// tab routing (hash-based, default overview)
const panes=[...document.querySelectorAll('.tabpane')];
const hashTabs=[...document.querySelectorAll('.tab[href^="#"]')];
function setTab(){
 let h=location.hash.slice(1)||'overview';
 if(!panes.some(p=>p.dataset.tab===h))h='overview';
 panes.forEach(p=>p.classList.toggle('active',p.dataset.tab===h));
 hashTabs.forEach(t=>{
  if(t.getAttribute('href')==='#'+h)t.setAttribute('aria-current','page');
  else t.removeAttribute('aria-current');
 });
}
addEventListener('hashchange',()=>{setTab();scrollTo({top:0})});
setTab();

const COL = {DEF:'var(--def)',MID:'var(--mid)',FWD:'var(--fwd)',GKP:'var(--gkp)'};
const dsvg=document.getElementById('diff'),
      fsvg=document.getElementById('frontier'), tip = document.getElementById('tip');
const W=940,L=52,R=16,T=14;
const xmax=Math.max(...DATA.map(d=>d.c))+0.4, xmin=3.6;
const ymax=Math.max(...DATA.map(d=>d.x))+0.4, ymin=0;
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
const CHART_MIN=1.8;  // charts hide sub-threshold players (unless in your squad)
const show=(d,f)=>(f==='All'||d.p===f)&&(d.x>=CHART_MIN||d.v4);
function mark(d,i,cx,cy,extra){
 const c=COL[d.p];
 const m = d.p==='GKP'
  ? `<rect x="${cx-4}" y="${cy-4}" width="8" height="8" fill="${c}"${extra||''}/>`
  : `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${c}"${extra||''}/>`;
 return `<g class="dot" data-i="${i}">${d.v4?`<circle cx="${cx}" cy="${cy}" r="8.5" fill="none" stroke="var(--ink)" stroke-width="1.6"/>`:''}${m}<circle cx="${cx}" cy="${cy}" r="13" fill="transparent"/></g>`;
}

// planner: per-GW projections, toggle total vs per-£m
const PLN_N = {GKP:5, DEF:15, MID:20, FWD:10};
let plnMode = 'total';
function drawPlanner(){
 const t=document.getElementById('planner');
 let h=`<tr><th>Player</th><th>Team</th><th class="num">£m</th>`+
  GWL.map(g=>`<th class="num">GW${g}</th>`).join('')+
  `<th class="num">${plnMode==='total'?'▼ ':''}Total</th><th class="num">${plnMode==='perm'?'▼ ':''}per £m</th></tr>`;
 ['GKP','DEF','MID','FWD'].forEach(p=>{
  const rows=DATA.filter(d=>d.p===p&&d.tt>0)
   .sort((a,b)=>plnMode==='total'?b.tt-a.tt:(b.tt/b.c)-(a.tt/a.c))
   .slice(0,PLN_N[p]);
  h+=`<tr><th colspan="${5+GWL.length}" style="padding-top:12px;color:${COL[p]}">${p}</th></tr>`;
  rows.forEach(d=>{
   h+=`<tr><td>${d.v4?'● ':''}<b>${esc(d.n)}</b></td><td>${d.t}</td><td class="num">${d.c.toFixed(1)}</td>`+
    d.g.map(v=>`<td class="num">${v.toFixed(1)}</td>`).join('')+
    `<td class="num"><b>${d.tt.toFixed(1)}</b></td><td class="num">${(d.tt/d.c).toFixed(2)}</td></tr>`;
  });
 });
 t.innerHTML=h;
}
(function(){
 const box=document.getElementById('plannerchips');
 [['total','Top by total xPts'],['perm','Top by xPts per £m']].forEach(([k,lbl],idx)=>{
  const b=document.createElement('button');
  b.className='chip';b.setAttribute('aria-pressed',idx===0?'true':'false');
  b.textContent=lbl;
  b.onclick=()=>{plnMode=k;box.querySelectorAll('.chip').forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');drawPlanner()};
  box.appendChild(b);
 });
})();

function drawDiff(f){
 const H=440,B=44,TT=20,SMAX=80;
 const SX=v=>L+Math.sqrt(v/SMAX)*(W-L-R), SY=v=>H-B-(v-0)/(ymax-0)*(H-TT-B);
 let g='';
 [1,5,15,40,75].forEach(v=>{g+=`<line x1="${SX(v)}" x2="${SX(v)}" y1="${TT}" y2="${H-B}" stroke="var(--grid)"/>`+
  `<text x="${SX(v)}" y="${H-B+18}" text-anchor="middle" font-size="11" fill="var(--muted)">${v}%</text>`});
 for(let p=1;p<=ymax;p++) g+=`<text x="${L-8}" y="${SY(p)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${p}</text>`;
 g+=`<line x1="${L}" x2="${W-R}" y1="${SY(0)}" y2="${SY(0)}" stroke="var(--axis)"/>`;
 g+=`<line x1="${SX(15)}" x2="${SX(15)}" y1="${TT}" y2="${H-B}" stroke="var(--axis)" stroke-dasharray="4 4"/>`;
 g+=`<line x1="${L}" x2="${W-R}" y1="${SY(3.2)}" y2="${SY(3.2)}" stroke="var(--axis)" stroke-dasharray="4 4"/>`;
 g+=`<text x="${L+8}" y="${TT+14}" font-size="11" fill="var(--muted)" font-weight="700" letter-spacing=".08em">DIFFERENTIALS</text>`;
 g+=`<text x="${W-R-8}" y="${TT+14}" text-anchor="end" font-size="11" fill="var(--muted)" font-weight="700" letter-spacing=".08em">ESSENTIALS</text>`;
 g+=`<text x="${W-R-8}" y="${H-B-10}" text-anchor="end" font-size="11" fill="var(--muted)" font-weight="700" letter-spacing=".08em">TRAPS</text>`;
 g+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" font-size="11.5" fill="var(--ink2)">Ownership (%)</text>`;
 DATA.forEach((d,i)=>{
  if(!show(d,f))return;
  g+=mark(d,i,SX(Math.min(d.s,SMAX)),SY(d.x));
 });
 dsvg.innerHTML=g;
}

function drawFrontier(f){
 const H=460,B=44;
 const X=v=>L+(v-xmin)/(xmax-xmin)*(W-L-R), Y=v=>H-B-(v-ymin)/(ymax-ymin)*(H-T-B);
 let g='';
 for(let p=Math.ceil(ymin);p<=ymax;p++) g+=`<line x1="${L}" x2="${W-R}" y1="${Y(p)}" y2="${Y(p)}" stroke="var(--grid)"/>`+
  `<text x="${L-8}" y="${Y(p)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${p}</text>`;
 for(let c=4;c<=xmax;c+=1) g+=`<text x="${X(c)}" y="${H-B+18}" text-anchor="middle" font-size="11" fill="var(--muted)">£${c}</text>`;
 g+=`<line x1="${L}" x2="${W-R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/>`;
 g+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" font-size="11.5" fill="var(--ink2)">Price (£m)</text>`;
 // faint field
 DATA.forEach((d,i)=>{
  if(!show(d,f))return;
  g+=`<g class="dot" data-i="${i}" opacity="0.22">${d.p==='GKP'?`<rect x="${X(d.c)-3.5}" y="${Y(d.x)-3.5}" width="7" height="7" fill="${COL[d.p]}"/>`:`<circle cx="${X(d.c)}" cy="${Y(d.x)}" r="3.8" fill="${COL[d.p]}"/>`}<circle cx="${X(d.c)}" cy="${Y(d.x)}" r="10" fill="transparent"/></g>`;
 });
 // running-best frontier: sorted by price, keep only new maxima
 const sorted=DATA.map((d,i)=>({d,i})).filter(o=>show(o.d,f)&&o.d.x>0)
  .sort((a,b)=>a.d.c-b.d.c||b.d.x-a.d.x);
 const fr=[]; let best=-1;
 sorted.forEach(o=>{if(o.d.x>best){best=o.d.x;fr.push(o)}});
 if(fr.length){
  let path=`M ${X(fr[0].d.c)} ${Y(fr[0].d.x)}`;
  for(let k=1;k<fr.length;k++) path+=` L ${X(fr[k].d.c)} ${Y(fr[k-1].d.x)} L ${X(fr[k].d.c)} ${Y(fr[k].d.x)}`;
  g+=`<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.6" opacity="0.75"/>`;
  fr.forEach(o=>{
   g+=mark(o.d,o.i,X(o.d.c),Y(o.d.x));
   g+=`<text x="${X(o.d.c)+9}" y="${Y(o.d.x)-7}" font-size="10.5" font-weight="600" fill="var(--ink2)">${esc(o.d.n)}</text>`;
  });
 }
 fsvg.innerHTML=g;
}

function bindTips(el){
 el.addEventListener('pointermove',e=>{
  const t=e.target.closest('.dot');
  if(!t){tip.style.opacity=0;return}
  const d=DATA[+t.dataset.i];
  tip.innerHTML=`<b>${esc(d.n)}</b> <span class="r">${d.t} · ${d.p}</span><br>£${d.c.toFixed(1)}m · <b>${d.x}</b> xPts (next 4 GWs) · GW1: <b>${d.xn}</b><br><span class="r">${d.s}% owned${d.v4?' · in your squad':''}</span>`;
  tip.style.opacity=1;
  tip.style.left=Math.min(e.clientX+14,innerWidth-250)+'px';
  tip.style.top=(e.clientY+14)+'px';
 });
 el.addEventListener('pointerleave',()=>tip.style.opacity=0);
}
bindTips(dsvg);bindTips(fsvg);

function radios(id, fn){
 const box=document.getElementById(id);
 if(!box)return;
 ['All','DEF','MID','FWD','GKP'].forEach((p,idx)=>{
  const b=document.createElement('button');
  b.className='chip';b.dataset.p=p;
  b.setAttribute('aria-pressed', idx===0 ? 'true' : 'false');
  b.innerHTML=(p==='All'?'':`<span class="sw" style="background:${COL[p]}"></span>`)+p;
  b.onclick=()=>{
   box.querySelectorAll('.chip').forEach(x=>x.setAttribute('aria-pressed','false'));
   b.setAttribute('aria-pressed','true');
   fn(p);
  };
  box.appendChild(b);
 });
}
radios('chips2', drawDiff);
radios('chips3', drawFrontier);
const ht=document.getElementById('heatmap');
ht.innerHTML='<tr><th></th>'+[1,2,3,4,5,6].map(g=>`<th class="num" style="text-align:center">GW${g}</th>`).join('')+'</tr>'+
 HEAT.map(r=>'<tr><td class="teamlab">'+r.team+'</td>'+r.gws.map(g=>g?`<td><div class="cell d${g.d}">${g.h?g.o.toUpperCase():g.o.toLowerCase()}</div></td>`:'<td></td>').join('')+'</tr>').join('');
// Overview panels driven by the squad saved on this device
function squadPanels(rows){
 const sec=document.getElementById('mysec');
 if(!sec||!rows.length)return;
 sec.hidden=false;
 const ns=document.getElementById('nosquadsec'); if(ns)ns.hidden=true;
 const HM=Object.fromEntries(HEAT.map(r=>[r.team,r.gws]));
 const opp=t=>{const g=(HM[t]||[])[GWL[0]-1];return g?`${g.o} (${g.h?'H':'A'})`:'—'};

 // captain: best single-fixture projection in the squad
 const caps=[...rows].sort((a,b)=>b.xn-a.xn).slice(0,3);
 document.getElementById('capbox').innerHTML='<div class="mini">'+caps.map((r,i)=>
  `<div class="row"><span>${i===0?'<b>':''}${esc(r.n)}${i===0?'</b>':''} `+
  `<span style="color:var(--muted)">${r.t} · ${opp(r.t)}</span></span>`+
  `<span${i===0?' class="up"':''}>${r.xn.toFixed(2)}</span></div>`).join('')+'</div>'+
  `<p class="note" style="margin:8px 0 0">GW${GWL[0]} projection, single fixture.</p>`;

 // transfers: best legal same-position upgrade within each player's own price
 const owned=new Set(rows.map(r=>r.n+'|'+r.t));
 const clubs={}; rows.forEach(r=>clubs[r.t]=(clubs[r.t]||0)+1);
 const ideas=[];
 rows.forEach(r=>{
  let best=null;
  for(const d of DATA){
   if(d.p!==r.p||d.c>r.c||owned.has(d.n+'|'+d.t))continue;
   const cc=(clubs[d.t]||0)-(d.t===r.t?1:0);
   if(cc>=3)continue;
   if(!best||d.tt>best.tt)best=d;
  }
  if(best&&best.tt-r.tt>0.5)ideas.push({o:r,i:best,gain:best.tt-r.tt});
 });
 ideas.sort((a,b)=>b.gain-a.gain);
 document.getElementById('trbox').innerHTML = ideas.length
  ? '<div class="mini">'+ideas.slice(0,3).map(v=>
     `<div class="row"><span>${esc(v.o.n)} → <b>${esc(v.i.n)}</b> `+
     `<span style="color:var(--muted)">${v.i.t} £${v.i.c.toFixed(1)}</span></span>`+
     `<span class="up">+${v.gain.toFixed(1)}</span></div>`).join('')+'</div>'+
     '<p class="note" style="margin:8px 0 0">4-week gain, same position, no extra spend.</p>'
  : '<p class="note">No upgrade beats what you own at these prices.</p>';

 // price watch: FPL's own projections, your players first
 const mine=rows.filter(r=>{const d=DATA.find(x=>x.n===r.n&&x.t===r.t);return d&&(Math.abs(d.pc)>=25||d.pl>=0.3)})
   .map(r=>DATA.find(x=>x.n===r.n&&x.t===r.t));
 const global=[...DATA].filter(d=>Math.abs(d.pc)>=50).sort((a,b)=>Math.abs(b.pc)-Math.abs(a.pc)).slice(0,3);
 const list=(mine.length?mine:global).slice(0,4);
 document.getElementById('pwbox').innerHTML = list.length
  ? '<div class="mini">'+list.map(d=>{
     const dir=d.pc>=0?'up':'down';
     return `<div class="row"><span>${esc(d.n)} <span style="color:var(--muted)">${d.t} £${d.c.toFixed(1)}</span></span>`+
      `<span class="${dir}">${d.pc>=0?'▲':'▼'} ${Math.abs(d.pc).toFixed(0)}%</span></div>`}).join('')+'</div>'+
     `<p class="note" style="margin:8px 0 0">${mine.length?'Your players':'Nobody in your squad is moving — biggest movers overall'} · FPL's own price-change progress.</p>`
  : '<p class="note">No price moves projected yet — this fills in once transfers start flowing.</p>';
}

function renderSquadTable(rows, el){
 let h=`<thead><tr><th>Player</th><th>Team</th><th>Pos</th><th class="num">£m</th>`+
  GWL.map(g=>`<th class="num">GW${g}</th>`).join('')+`<th class="num">Total</th><th>Role</th></tr></thead><tbody>`;
 let benchMarked=false;
 rows.forEach(r=>{
  const bs=!r.xi&&!benchMarked?(benchMarked=true,' benchstart'):'';
  h+=`<tr class="${r.xi?'xi':''}${bs}"><td><b>${esc(r.n)}</b></td><td>${r.t}</td><td>${r.p}</td><td class="num">${r.c.toFixed(1)}</td>`+
   r.g.map(v=>`<td class="num">${v.toFixed(1)}</td>`).join('')+
   `<td class="num"><b>${r.tt.toFixed(1)}</b></td><td><span class="pill">${r.xi?'XI':'Bench'}</span></td></tr>`;
 });
 const xi=rows.filter(r=>r.xi);
 const sums=GWL.map((_,k)=>xi.reduce((s,r)=>s+r.g[k],0));
 const total=sums.reduce((a,b)=>a+b,0);
 h+=`</tbody><tfoot><tr><th colspan="4" style="text-align:left;color:var(--ink)">Starting XI</th>`+
  sums.map(v=>`<th class="num" style="color:var(--ink)">${v.toFixed(1)}</th>`).join('')+
  `<th class="num" style="color:var(--accent)">${total.toFixed(1)}</th><th></th></tr></tfoot>`;
 el.innerHTML=h;
 const tile=document.getElementById('tile-squad');
 if(tile){tile.hidden=false;document.getElementById('tile-squad-v').textContent=total.toFixed(1)}
}
const sqEl=document.getElementById('squad');
if(sqEl&&SQUAD.length)renderSquadTable(SQUAD, sqEl);

// public pages only: light up the squad saved on this device by the analyzer
if(!SQUAD.length){(function(){
 try{
  const s=localStorage.getItem('fpl_my_squad'); if(!s)return;
  const idx=new Map(DATA.map((d,i)=>[d.n+'|'+d.t,i]));
  const rows=[];
  JSON.parse(s).forEach(line=>{
   const parts=line.trim().split(' '), t=parts.pop(), n=parts.join(' ');
   const i=idx.get(n+'|'+t);
   if(i!=null){DATA[i].v4=true; rows.push(DATA[i]);}
  });
  if(!rows.length)return;
  const minR={GKP:1,DEF:3,MID:2,FWD:1}, maxR={GKP:1,DEF:5,MID:5,FWD:3};
  const order=[...rows].sort((a,b)=>b.tt-a.tt); const xi=new Set();
  for(const pos in minR) order.filter(r=>r.p===pos).slice(0,minR[pos]).forEach(r=>xi.add(r));
  for(const r of order){ if(xi.size>=11)break;
   if(!xi.has(r)&&[...xi].filter(x=>x.p===r.p).length<maxR[r.p]) xi.add(r);}
  rows.forEach(r=>r.xi=xi.has(r));
  squadPanels(rows);
  const POSORD={GKP:0,DEF:1,MID:2,FWD:3};
  const sec=document.getElementById('mysquadsec');
  if(sec){
   sec.hidden=false;
   document.getElementById('mysquadnote').textContent=
    'Saved on this device from the analyzer ('+rows.length+' players). '+
    'Rings and ● across the page mark your squad; XI below is the model\\u2019s pick.';
   renderSquadTable(rows.sort((a,b)=>(a.xi?0:1)-(b.xi?0:1)||POSORD[a.p]-POSORD[b.p]),
                    document.getElementById('mysquad'));
  }
 }catch(e){}
})()}
drawDiff('All');drawFrontier('All');drawPlanner();
</script>
"""
POS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
mins_by_id = {e['id']: e['minutes'] for e in ns['d']['elements']}


def table_rows(rows):
    return ''.join(f"<tr><td><b>{p['name']}</b></td><td>{teams[p['team']]}</td>"
                   f"<td class='num'>{p['price']:.1f}</td><td class='num'>{p['sel']:.1f}</td>"
                   f"<td class='num'><b>{p['xpts']:.2f}</b></td></tr>" for p in rows)


diffs = sorted((p for p in players if p['sel'] < 10 and p['price'] >= 4.5),
               key=lambda p: -p['xpts'])[:8]
# traps: only players the model has real data on (900+ prior-season minutes),
# so cold-start price priors don't get mislabeled as traps
trapped = sorted((p for p in players if p['sel'] >= 15 and p['xpts'] < 3.2
                  and mins_by_id.get(p['id'], 0) >= 900),
                 key=lambda p: -p['sel'])[:8]

# best players per price band per position (value-for-money tables)
# exact 0.5m price points; only the sparse premium tail is grouped
BANDS = {
    1: [(4.0, 4.0, 3), (4.5, 4.5, 3), (5.0, 5.0, 3), (5.5, 6.5, 3)],
    2: [(4.0, 4.0, 3), (4.5, 4.5, 3), (5.0, 5.0, 3), (5.5, 5.5, 3),
        (6.0, 6.0, 3), (6.5, 8.5, 5)],
    3: [(4.5, 4.5, 3), (5.0, 5.0, 3), (5.5, 5.5, 3), (6.0, 6.0, 3),
        (6.5, 6.5, 3), (7.0, 7.0, 3), (7.5, 7.5, 3), (8.0, 8.0, 3),
        (8.5, 9.5, 3), (10.0, 16.0, 3)],
    4: [(4.5, 4.5, 3), (5.0, 5.0, 3), (5.5, 5.5, 3), (6.0, 6.0, 3),
        (6.5, 6.5, 3), (7.0, 7.0, 3), (7.5, 7.5, 3), (8.0, 8.0, 3),
        (8.5, 16.0, 5)],
}


def band_tables(personal):
    v4set = set(V4_XI) | set(V4_BENCH)
    cols = []
    for pos_id in [2, 3, 4, 1]:
        rows = ''
        for lo, hi, n in BANDS[pos_id]:
            cand = sorted((p for p in players if p['pos'] == pos_id
                           and lo <= p['price'] <= hi and p['xmins'] >= 45),
                          key=lambda p: -p['xpts'])[:n]
            if not cand:
                continue
            if lo == hi:
                label = f'£{lo:.1f}'
            elif hi >= 15.9:
                label = f'£{lo:.1f}+'
            else:
                label = f'£{lo:.1f}–{hi:.1f}'
            rows += (f"<tr><th colspan='4' style='padding-top:10px'>{label}</th></tr>"
                     + ''.join(
                f"<tr><td>{'● ' if personal and pkey(p) in v4set else ''}<b>{p['name']}</b> "
                f"<span style='color:var(--muted)'>{teams[p['team']]}</span></td>"
                f"<td class='num'>{p['price']:.1f}</td><td class='num'>{p['sel']:.0f}%</td>"
                f"<td class='num'><b>{p['xpts']:.2f}</b></td></tr>" for p in cand))
        cols.append(f"<div><h3>{pos_name[pos_id]}</h3><div class='scroll'><table>"
                    f"<tr><th>Player</th><th class='num'>£m</th><th class='num'>Own</th>"
                    f"<th class='num'>xPts</th></tr>{rows}</table></div></div>")
    note = ('<p class="note" style="margin:8px 0 0">● = our squad. ' if personal else
            '<p class="note" style="margin:8px 0 0">')
    return ('<section class="card"><h2>Best at every price point</h2>'
            '<p class="note">The frontier chart shows every player faintly, with the best score at '
            'each price bolded, named, and joined by a running-best line — anyone ON the line is '
            'the strongest buy at that money. Tables list the top names per 0.5m shelf. '
            'Only players expected to start (45+ expected minutes).</p>'
            '<div class="chips" id="chips3"></div>'
            '<svg id="frontier" viewBox="0 0 940 460" role="img" aria-label="Value frontier: expected points against price"></svg>'
            f"<div class='cols' style='margin-top:18px'><div class='stack'>{cols[0]}{cols[2]}</div><div class='stack'>{cols[1]}{cols[3]}</div></div>"
            + note + 'Scores are per team gameweek and price in availability.</p></section>')


SQUAD_SEC = """<section class="card">
 <h2>Squad v5 — £100.0m</h2>
 <p class="note">Starting XI then bench, projected per gameweek against actual fixtures. The footer row sums the starting XI.</p>
 <div class="scroll"><table id="squad"></table></div>
</section>"""

# (the public "Your squad" table was superseded by the Optimal Model Squad
# section — saved squads still get chart rings/● via the personalize script,
# and their full table lives behind the My Team nav link)


from datetime import datetime, timedelta, timezone

# 4-week transfer-plan optimizer (skipped gracefully if the solver fails)
OPT = None
try:
    import plan4
    _plan = plan4.solve_plan(players, n_gw=len(gw_labels))
    if _plan:
        _pool = _plan['pool']
        _ogws = [[{'n': _pool[s['id']]['name'], 't': teams[_pool[s['id']]['team']],
                   'p': pos_name[_pool[s['id']]['pos']], 'c': _pool[s['id']]['price'],
                   'g': _pool[s['id']]['gws'], 'xi': s['xi'], 'cap': s['cap']}
                  for s in squad] for squad in _plan['gws']]
        _otr = [{'out': [{'n': _pool[i]['name'], 't': teams[_pool[i]['team']]} for i in m['out']],
                 'in': [{'n': _pool[i]['name'], 't': teams[_pool[i]['team']]} for i in m['in']],
                 'hits': m['hits']} for m in _plan['transfers']]
        _tot = []
        for g, squad in enumerate(_plan['gws']):
            xi_ids = [s['id'] for s in squad if s['xi']]
            t = sum(_pool[i]['gws'][g] for i in xi_ids)
            t += sum(_pool[s['id']]['gws'][g] for s in squad if s['cap'])
            _tot.append(round(t, 1))
        OPT = {'gws': _ogws, 'transfers': _otr, 'totals': _tot,
               'hitpen': sum(m['hits'] for m in _plan['transfers']) * 4}
        print(f"plan4: {_plan['status']}, 4-GW plan total {sum(_tot) - OPT['hitpen']:.1f}")
        # publish the optimum as a selectable squad (the Squads tab shows it as
        # a permanent 🤖 entry; roles encode its GW1 XI and captain)
        _gw1 = _ogws[0]
        _roles = ''.join('C' if r['cap'] else ('X' if r['xi'] else 'B') for r in _gw1)
        _weeks = [[{'n': r['n'], 't': r['t'], 'pos': r['p'], 'price': r['c'],
                    'gws': r['g'], 'xi': r['xi'], 'cap': r['cap']} for r in wk]
                  for wk in _ogws]
        json.dump({'ts': datetime.now(timezone.utc).isoformat(timespec='minutes'),
                   'lines': [f"{r['n']} {r['t']}" for r in _gw1], 'roles': _roles,
                   'total': round(sum(_tot) - OPT['hitpen'], 1),
                   'weekly': _tot, 'transfers': _otr, 'weeks': _weeks},
                  open('optimal_squad.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
except Exception as _exc:  # noqa: BLE001 - dashboard must still build
    print('plan4 skipped:', _exc)

_ev = next(e for e in ns['d']['events'] if e['id'] == gw_labels[0])
_dl = datetime.strptime(_ev['deadline_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=1)  # UK summer time
tile_deadline = _dl.strftime('%a %d %b, %H:%M')
tile_dl_gw = f"GW{gw_labels[0]} · UK time"
_tv = max((p for p in players if p['xmins'] >= 45 and p['price'] > 0), key=lambda p: p['xpts'] / p['price'])
_ts = max(players, key=lambda p: p['xpts'])
_td = diffs[0]


import html as _html

# Overview: market movements from snapshot history, and the top news stories
_moves_html, _move_win, _stories_html = '', '', ''
try:
    import momentum as _mom
    _els = {e['id']: e for e in ns['d']['elements']}
    _ris, _fal, _meta = _mom.recent_moves(_els, teams, hours=6)

    def _mv_table(rows, label):
        if not rows:
            return f"<div><h3>{label}</h3><p class='note'>Nothing yet.</p></div>"
        body = ''.join(
            f"<tr><td><b>{_html.escape(r['player'].split('|')[0])}</b> "
            f"<span style='color:var(--muted)'>{r['player'].split('|')[1]}</span></td>"
            f"<td class='num'>{r['price']:.1f}</td><td class='num'>{r['sel']:.1f}</td>"
            f"<td class='num'>{r['d_sel']:+.2f}</td>"
            f"<td class='num'>{r['d_net']:+,}</td></tr>" for r in rows)
        return (f"<div><h3>{label}</h3><div class='scroll'><table><tr><th>Player</th>"
                f"<th class='num'>£m</th><th class='num'>Own%</th><th class='num'>Δ own</th>"
                f"<th class='num'>Δ net</th></tr>{body}</table></div></div>")

    if _meta['ready'] and (_ris or _fal):
        _moves_html = _mv_table(_ris, 'Moving in') + _mv_table(_fal, 'Moving out')
        _move_win = f"last {_meta['hours']:.0f}h"
    else:
        _moves_html = ("<p class='note'>Collecting baseline — movement appears once we have "
                       "a few hours of snapshots and the gameweek opens.</p>")
        _move_win = f"{_meta.get('snapshots', 0)} snapshots so far"
except Exception as _e:
    _moves_html = f"<p class='note'>Movements unavailable ({_html.escape(str(_e)[:60])}).</p>"

try:
    _news = json.load(open('news_cache.json', encoding='utf-8'))
    _picks = (_news.get('proposals') or [])[:3] + [
        {'player': d['player'], 'headline': d['items'][0]['title'],
         'source': d['items'][0]['source'], 'when': '', 'why': d['why']}
        for d in (_news.get('discoveries') or [])[:3] if d.get('items')]
    if _picks:
        _stories_html = ''.join(
            f"<div style='border-top:1px solid var(--grid);padding:9px 0'>"
            f"<b>{_html.escape(s['player'].split('|')[0])}</b> "
            f"<span style='color:var(--muted);font-size:12.5px'>{s['player'].split('|')[1]}"
            f" · {_html.escape(s.get('why',''))}</span>"
            f"<div style='font-size:13.5px'>“{_html.escape(s['headline'][:120])}”</div>"
            f"<div class='note' style='margin:0'>{_html.escape(s.get('source',''))}"
            f" {_html.escape(s.get('when',''))}</div></div>" for s in _picks)
    else:
        _stories_html = "<p class='note'>No flagged stories in the window.</p>"
except Exception:
    _stories_html = "<p class='note'>News sweep hasn't run yet.</p>"


def emit(path, personal):
    # public copy strips squad markers entirely (no rings, labels, table, or
    # flags in the embedded JSON) so nothing about our team leaks pre-deadline
    dat = data if personal else [{**r, 'v4': False, 'xi': False} for r in data]
    page = (html.replace('__VALUEBANDS__', band_tables(personal))
                .replace('__SQUADSEC__', SQUAD_SEC if personal else '')
                .replace('__MOVES__', _moves_html)
                .replace('__MOVEWIN__', _move_win)
                .replace('__STORIES__', _stories_html)
                .replace('__OPTTOTAL__', f"{OPT['totals'] and round(sum(OPT['totals']) - OPT['hitpen'], 1) or '–'}" if OPT else '–')
                .replace('__PULLED__', (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%a %d %b %H:%M'))
                .replace('__DL_TIME__', tile_deadline).replace('__DL_GW__', tile_dl_gw)
                .replace('__TV_NAME__', _tv['name'])
                .replace('__TV_SUB__', f"£{_tv['price']:.1f} · {_tv['xpts']:.2f} xPts · {teams[_tv['team']]}")
                .replace('__TD_NAME__', _td['name'])
                .replace('__TD_SUB__', f"{_td['sel']:.0f}% owned · {_td['xpts']:.2f} xPts · {teams[_td['team']]}")
                .replace('__TS_NAME__', _ts['name'])
                .replace('__TS_SUB__', f"{_ts['xpts']:.2f} xPts/match · {teams[_ts['team']]}")
                .replace('__SUBNOTE__', 'Squad v5 marked with rings. ' if personal else '')
                .replace('__RINGNOTE__', 'Ringed dots / ● = our squad. ' if personal else '')
                .replace('__DIFFROWS__', table_rows(diffs))
                .replace('__TRAPROWS__', table_rows(trapped))
                .replace('__GWL__', json.dumps(gw_labels))
                .replace('__DATA__', json.dumps(dat, ensure_ascii=False))
                .replace('__HEAT__', json.dumps(heat, ensure_ascii=False))
                .replace('__SQUAD__', json.dumps(squad_rows if personal else [], ensure_ascii=False)))
    open(path, 'w', encoding='utf-8').write(page)


emit('dashboard.html', False)      # public: general analysis only (served by app.py)
emit('my_dashboard.html', True)    # personal: includes squad v4 (artifact / local viewing)
print(f'dashboard.html (public) + my_dashboard.html (personal): {len(data)} players, {len(heat)} teams')
