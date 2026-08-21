"""Generate dashboard.html: self-contained FPL model dashboard.

Reuses model.py's scoring (exec'd up to the SCORES-END marker), inlines the
data as JSON, and writes a single static HTML file — servable from any
static host (home server, python -m http.server, nginx).
"""
import json
from collections import defaultdict

import theme

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
# fixture runs carry BOTH directions: 'a' is the attacking read (expected goals
# for, against that team's own average) and 'd' the defensive one (expected
# goals against). FPL's single 1-5 rating is kept only as a fallback label.
FIXMAP = ns.get('FIXMAP') or {}
runs = defaultdict(dict)
for f in fx:
    if not f['event'] or f['event'] > 6:
        continue
    for side, opp, home, fdr in ((f['team_h'], f['team_a'], 1, f['team_h_difficulty']),
                                 (f['team_a'], f['team_h'], 0, f['team_a_difficulty'])):
        c = teams[side]
        v = (FIXMAP.get(c) or {}).get(str(f['event'])) or {}
        runs[c][f['event']] = {
            'o': teams[opp], 'h': home, 'fdr': fdr,
            'a': v.get('af'), 'd': v.get('df'), 'gf': v.get('gf'),
            'ga': v.get('ga'), 'cs': v.get('cs'), 'q': 1 if v.get('src') == 'odds' else 0}
order = sorted(runs, key=lambda t: -sum(g['a'] or 1 for g in runs[t].values()))
heat = [{'team': t, 'gws': [runs[t].get(gw) for gw in range(1, 7)]} for t in order]
fixmeta = {k: v for k, v in (ns.get('FIXMETA') or {}).items()
           if k not in ('avg_gf', 'avg_ga')}

squad_rows = []
for name, club in V4_XI + V4_BENCH:
    p = next(q for q in players if q['name'] == name and teams[q['team']] == club)
    squad_rows.append({'n': name, 't': club, 'p': pos_name[p['pos']],
                       'c': p['price'], 'g': p['gws'], 'tt': p['tot4'],
                       'xi': (name, club) in set(V4_XI)})

html = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fleamarket Analytics</title>
__STYLE__
<div class="wrap">
<div class="brand"><span class="mark">Flea<em>market</em></span><span class="season">2026/27</span></div>
<nav class="tabs">
 <a class="tab" href="#overview">Overview</a>
 <a class="tab" href="#value">Value</a>
 <a class="tab" href="#planner">Planner</a>
 <a class="tab" href="#market">Market</a>
 <a class="tab" href="#fixtures">Fixtures</a>
 <a class="tab" href="#teams">Teams</a>
 <a class="tab" href="/news">News ↗</a>
 <a class="tab" href="/squads">Manager ↗</a>
</nav>

<div class="tabpane" data-tab="overview">
<p class="sub" style="margin-top:16px">Every player scored from last season's Opta rates (xG, xA,
clean sheets, defensive contributions), season expectations, and fixtures. __SUBNOTE__</p>
<div class="tiles">
 <div class="tile"><div class="tl">Next deadline</div><div class="tv">__DL_TIME__</div><div class="ts">__DL_GW__</div></div>
 <div class="tile"><div class="tl">Top value</div><div class="tv">__TV_NAME__</div><div class="ts">__TV_SUB__</div></div>
 <div class="tile"><div class="tl">Top differential</div><div class="tv">__TD_NAME__</div><div class="ts">__TD_SUB__</div></div>
 <div class="tile"><div class="tl">Model top scorer</div><div class="tv">__TS_NAME__</div><div class="ts">__TS_SUB__</div></div>
 <div class="tile"><div class="tl">Model optimum, 4 GWs</div><div class="tv">__OPTTOTAL__</div><div class="ts">__OPTSUB__ · <a href="/squads">open in Squads</a></div></div>
 <div class="tile" id="tile-squad" hidden><div class="tl">Your XI, next 4 GWs</div><div class="tv" id="tile-squad-v">–</div><div class="ts">model projection</div></div>
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

<div class="tabpane" data-tab="teams">
<section class="card">
 <h2>Summer window — who changed most</h2>
 <p class="note">Fees and moves from Wikipedia's English transfer list (__TRSRC__).
 Net spend counts permanent deals with a disclosed fee, so undisclosed and loan business is
 listed but not totalled. <b>Click a club</b> for its full ledger and a squad read.</p>
 <div class="scroll"><table id="teamtab"></table></div>
</section>

<section class="card" id="clubcard" hidden>
 <h2 id="clubname">Club</h2>
 <p class="note" id="clubmeta"></p>
 <div class="cols">
  <div><h3>Arrivals</h3><div id="clubin" class="mini"></div></div>
  <div><h3>Departures</h3><div id="clubout" class="mini"></div></div>
 </div>
 <h3 style="margin-top:20px">Where the squad stands</h3>
 <div class="scroll"><table id="clubpos"></table></div>
 <p class="note" id="clubcaveat" style="margin-top:10px"></p>
</section>
</div>

<div class="tabpane" data-tab="fixtures">
<section class="card">
 <h2>Opening fixtures — GW1–6</h2>
 <p class="note">A fixture is two different things at once. Coventry at home is a gift for
 attackers and a gift for your defenders; Fulham v Chelsea is a good week to own a Fulham
 forward and a bad one to own their back four. So each cell is scored twice — never
 collapsed into one difficulty number.</p>
 <div class="chips" id="hmview">
  <button class="chip" data-v="both" aria-pressed="true">Both</button>
  <button class="chip" data-v="att" aria-pressed="false">Attacking returns</button>
  <button class="chip" data-v="def" aria-pressed="false">Clean sheets</button>
 </div>
 <div class="scroll hm"><table id="heatmap"></table></div>
 <div class="hmkey">
  <span>Kind <span class="sc"><i class="f1"></i><i class="f2"></i><i class="f3"></i><i class="f4"></i><i class="f5"></i></span> Hostile</span>
  <span>Uppercase = home</span><span>Dot = priced by bookmakers</span>
 </div>
 <p class="note" id="hmnote" style="margin-top:10px"></p>
</section>
</div>

<footer>Phase 1 model: built on prior-season Opta rates, expected minutes, transfer
context, season expectations and fixtures — a value lens, not an oracle.
<br>FPL data pulled __PULLED__ UK · refreshed hourly · __ODDSNOTE__</footer>
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
// fixture grid, scored in two directions and never collapsed into one. Both
// bands are absolute expected goals so the colours mean the same thing in every
// row; the multiplier against that team's own average — which is what the xPts
// model actually applies — rides along in the tooltip.
const ht=document.getElementById('heatmap');
const aBand=v=>v==null?0:v>=1.90?1:v>=1.60?2:v>=1.30?3:v>=1.05?4:5;
const dBand=v=>v==null?0:v<=0.85?1:v<=1.10?2:v<=1.40?3:v<=1.75?4:5;
const aTip=g=>g.gf==null?'':`xGF ${g.gf.toFixed(2)} — ×${g.a.toFixed(2)} their average`;
const dTip=g=>g.ga==null?'':`xGA ${g.ga.toFixed(2)}, clean sheet ${Math.round(g.cs*100)}% — ×${g.d.toFixed(2)} their average`;
function hmCell(g,view){
 const lab=g.h?g.o.toUpperCase():g.o.toLowerCase(), q=g.q?' odds':'';
 if(view==='att')
  return `<div class="cell f${aBand(g.gf)}${q}" title="${aTip(g)}">${lab}<span class="cn">${g.gf==null?'':g.gf.toFixed(2)}</span></div>`;
 if(view==='def')
  return `<div class="cell f${dBand(g.ga)}${q}" title="${dTip(g)}">${lab}<span class="cn">${g.cs==null?'':Math.round(g.cs*100)+'%'}</span></div>`;
 return `<div class="cell f0${q}" title="${aTip(g)}\n${dTip(g)}">${lab}<span class="bars">`+
        `<i class="f${aBand(g.gf)}"></i><i class="f${dBand(g.ga)}"></i></span></div>`;
}
function drawHeat(view){
 const rank=r=>view==='def'
   ? r.gws.reduce((s,g)=>s+(g&&g.ga!=null?g.ga:1.4),0)                 // fewest conceded first
   : -r.gws.reduce((s,g)=>s+(g&&g.gf!=null?g.gf:1.35),0);              // most scored first
 const rows=[...HEAT].sort((x,y)=>rank(x)-rank(y));
 ht.innerHTML='<tr><th></th>'+[1,2,3,4,5,6].map(g=>`<th class="num" style="text-align:center">GW${g}</th>`).join('')+'</tr>'+
  rows.map(r=>'<tr><td class="teamlab">'+r.team+'</td>'+
   r.gws.map(g=>g?'<td>'+hmCell(g,view)+'</td>':'<td></td>').join('')+'</tr>').join('');
 const note=document.getElementById('hmnote');
 if(note)note.textContent=view==='att'
  ? 'Most expected goals first. Cells show expected goals for, set by how leaky the opponent is — hover for the multiplier against that club’s own average, which is what the projection applies to a player’s xG/90.'
  : view==='def'
  ? 'Tightest run first. Cells show clean-sheet probability from expected goals against, set by how dangerous the opponent is — a different question from whether the fixture looks winnable.'
  : 'Two bars per fixture: left is attacking returns, right is clean sheets. Where they disagree — a leaky opponent who still carries a threat — one difficulty number could never have told you both. Sorted by attacking run.';
}
let hmView='both';
drawHeat(hmView);
document.querySelectorAll('#hmview .chip').forEach(b=>b.onclick=()=>{
 hmView=b.dataset.v;
 document.querySelectorAll('#hmview .chip').forEach(o=>o.setAttribute('aria-pressed',o===b));
 drawHeat(hmView);
});
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

// ---- Teams tab -----------------------------------------------------------
const TEAMS=__TEAMS__;
if(TEAMS.length){
 const fm=v=>v==null?'–':(v>=0?'+':'')+'£'+Math.abs(v).toFixed(1)+'m';
 const feeTxt=p=>p.loan?'loan':(p.fee?('£'+(p.fee/1e6).toFixed(1)+'m'):(p.label||'undisclosed'));
 let sortKey='net';
 function drawTeams(){
  const rows=[...TEAMS].sort((a,b)=>(b[sortKey]??-1e9)-(a[sortKey]??-1e9));
  let h='<thead><tr><th>Club</th><th class="num">In</th><th class="num">Out</th>'+
   '<th class="num">Spent</th><th class="num">Received</th><th class="num">Net</th>'+
   '<th class="num" title="thousands of prior-season Premier League minutes in the current squad">PL mins</th><th class="num">Squad xPts</th>'+
   '<th class="num">Last</th><th class="num">Pred</th></tr></thead><tbody>';
  rows.forEach(t=>{
   const d=(t.pred!=null&&t.last!=null)?t.pred-t.last:null;
   h+=`<tr data-c="${t.c}" style="cursor:pointer"><td><b>${t.c}</b></td>`+
    `<td class="num">${t.in.length}</td><td class="num">${t.out.length}</td>`+
    `<td class="num">${t.spend?fm(t.spend).replace('+',''):'–'}</td>`+
    `<td class="num">${t.recv?fm(t.recv).replace('+',''):'–'}</td>`+
    `<td class="num ${t.net>0?'down':(t.net<0?'up':'')}">${fm(t.net)}</td>`+
    `<td class="num">${t.cont}k</td><td class="num"><b>${t.squad_xp.toFixed(1)}</b></td>`+
    `<td class="num">${t.last??'–'}</td>`+
    `<td class="num">${t.pred??'–'}${d!=null?` <span class="${d>0?'up':(d<0?'down':'')}">${d>0?'+':''}${d}</span>`:''}</td></tr>`;
  });
  h+='</tbody>';
  document.getElementById('teamtab').innerHTML=h;
 }
 function showClub(c){
  const t=TEAMS.find(x=>x.c===c); if(!t)return;
  document.getElementById('clubcard').hidden=false;
  document.getElementById('clubname').textContent=c+' — summer window';
  const d=(t.pred!=null&&t.last!=null)?t.pred-t.last:null;
  document.getElementById('clubmeta').innerHTML=
   `Net spend <b>${fm(t.net)}</b> · ${t.in.length} in, ${t.out.length} out · `+
   `<b>${t.cont}k</b> minutes of prior Premier League experience in the squad`+
   (d!=null?` · market expects <b class="${d>0?'up':'down'}">${d>0?'+':''}${d} pts</b> on last season`:'');
  const list=(arr,dir)=>arr.length?arr.map(p=>
    `<div class="row"><span>${p.pos?`<span class="pill">${p.pos}</span> `:''}<b>${esc(p.n)}</b> `+
    `<span style="color:var(--muted)">${dir} ${esc(p.other||'?')}</span></span>`+
    `<span>${feeTxt(p)}${p.xp!=null?` · <b>${p.xp.toFixed(2)}</b>`:''}</span></div>`).join('')
   :'<p class="note">None recorded.</p>';
  document.getElementById('clubin').innerHTML=list(t.in,'from');
  document.getElementById('clubout').innerHTML=list(t.out,'to');
  // position read: squad strength now, and what moved in each position
  const order=['GKP','DEF','MID','FWD'];
  let ph='<thead><tr><th>Area</th><th class="num">Starters xPts</th><th class="num">League rank</th>'+
   '<th class="num">In</th><th class="num">Out</th><th>Verdict</th></tr></thead><tbody>';
  order.forEach(pos=>{
   const mine=t.pos[pos];
   const ranked=[...TEAMS].sort((a,b)=>b.pos[pos]-a.pos[pos]);
   const rank=ranked.findIndex(x=>x.c===t.c)+1;
   const ins=t.in.filter(p=>p.pos===pos), outs=t.out.filter(p=>p.pos===pos);
   const inXp=ins.reduce((s,p)=>s+(p.xp||0),0);
   let verdict='steady', cls='';
   if(ins.length&&inXp>=3.5){verdict='rebuilt — '+ins.map(p=>p.n.split(' ').pop()).join(', ');cls='up'}
   else if(ins.length>outs.length){verdict='added depth';cls=''}
   else if(outs.length>ins.length){verdict='thinner on paper';cls='down'}
   ph+=`<tr><td><b>${pos}</b></td><td class="num">${mine.toFixed(1)}</td>`+
    `<td class="num">${rank}/20</td><td class="num">${ins.length}</td><td class="num">${outs.length}</td>`+
    `<td class="${cls}">${esc(verdict)}</td></tr>`;
  });
  ph+='</tbody>';
  document.getElementById('clubpos').innerHTML=ph;
  const unknown=t.out.filter(p=>p.pos==null).length;
  document.getElementById('clubcaveat').textContent=
   'Starters xPts sums the best expected XI slots per area (1 GK, 4 DEF, 4 MID, 2 FWD) from the model. '+
   (unknown?unknown+' departure(s) left the league, so their position and prior output are unknown to the model — '
    :'')+'departures who moved within the league keep their model score.';
  document.getElementById('clubcard').scrollIntoView({behavior:'smooth',block:'nearest'});
 }
 document.getElementById('teamtab').addEventListener('click',e=>{
  const tr=e.target.closest('tr[data-c]'); if(tr)showClub(tr.dataset.c);
 });
 drawTeams();
}

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
        _nhit = sum(m['hits'] for m in _plan['transfers'])
        _nft = sum(len(m['in']) for m in _plan['transfers']) - _nhit
        OPT = {'gws': _ogws, 'transfers': _otr, 'totals': _tot,
               'hitpen': _nhit * 4, 'ftspent': _nft, 'ftvalue': plan4.FT_VALUE}
        print(f"plan4: {_plan['status']}, 4-GW plan total {sum(_tot) - OPT['hitpen']:.1f} "
              f"({_nft} free transfers spent at {plan4.FT_VALUE} each, {_nhit} hits)")
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
                   'ftspent': _nft, 'ftvalue': plan4.FT_VALUE,
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



# ---- Teams tab: transfer ledger joined to squad strength -------------------
TEAMS, TR_SRC = [], 'not fetched'
try:
    import transfers as _tr
    _led = _tr.load() or _tr.fetch()
    TR_SRC = _led.get('ts', '')[:16].replace('T', ' ') + ' UTC'
    _sent = {}
    try:
        _sj = json.load(open('team_sentiment.json', encoding='utf-8'))
        _sent = {k: v for k, v in _sj.items() if not k.startswith('_')}
    except Exception:
        pass
    _byclub = {}
    for _p in players:
        _byclub.setdefault(teams[_p['team']], []).append(_p)
    _name_idx = {}
    for _p in players:
        _name_idx.setdefault(_p['name'].lower(), []).append(_p)

    def _match(nm, club=None):
        """Find an FPL player for a transfer-list name (surname match)."""
        sur = nm.split()[-1].lower()
        pool = _byclub.get(club, players) if club else players
        for q in pool:
            n = q['name'].lower()
            if sur in n or n in sur:
                return q
        return None

    STARTERS = {'GKP': 1, 'DEF': 4, 'MID': 4, 'FWD': 2}
    for short in sorted(_byclub):
        d = (_led.get('clubs') or {}).get(short) or {'in': [], 'out': [], 'spend': 0,
                                                     'received': 0, 'net': 0}
        squad = _byclub[short]
        # squad strength: best expected starters per position
        pos_now = {}
        for pos, n in STARTERS.items():
            best = sorted([q for q in squad if pos_name[q['pos']] == pos],
                          key=lambda q: -q['xpts'])[:n]
            pos_now[pos] = round(sum(q['xpts'] for q in best), 1)
        # prior Premier League minutes still in the building (continuity proxy)
        mins = sum(ns['d']['elements'][0].get('minutes', 0) * 0 for _ in [0])
        el_by_id = {e['id']: e for e in ns['d']['elements']}
        mins = sum(el_by_id[q['id']]['minutes'] for q in squad if q['id'] in el_by_id)
        cont = round(mins / 1000)   # thousands of prior PL minutes in the squad

        def _dec(lst, club):
            out = []
            for x in lst:
                q = _match(x['name'], club)
                out.append({'n': x['name'], 'other': x['other'], 'fee': x['fee'],
                            'label': x['label'], 'loan': x['loan'],
                            'pos': pos_name[q['pos']] if q else None,
                            'xp': round(q['xpts'], 2) if q else None})
            return out

        TEAMS.append({
            'c': short, 'in': _dec(d['in'], short), 'out': _dec(d['out'], None),
            'spend': round(d['spend'] / 1e6, 1), 'recv': round(d['received'] / 1e6, 1),
            'net': round(d['net'] / 1e6, 1), 'pos': pos_now, 'cont': cont,
            'last': (_sent.get(short) or {}).get('last'),
            'pred': (_sent.get(short) or {}).get('pred'),
            'squad_xp': round(sum(pos_now.values()), 1),
        })
    print(f'teams tab: {len(TEAMS)} clubs, ledger {TR_SRC}')
except Exception as _e:
    print('teams tab data skipped:', _e)


import html as _html

try:
    _oc = json.load(open('odds_cache.json', encoding='utf-8'))
    _n_odds = len([f for f in _oc.get('fixtures', []) if f.get('event')])
    _odds_note = (f"fixtures priced by bookmaker odds: {_n_odds}"
                  if _n_odds else 'fixture difficulty from FPL ratings (no odds posted yet)')
except Exception:
    _odds_note = 'fixture difficulty from FPL ratings'
# the optimum's transfer economics, so the headline number is explainable: a
# plan that holds is a result, not a missing feature
if OPT:
    _nt = sum(len(t['in']) for t in OPT['transfers'])
    _opt_sub = ('holds all 4 weeks' if not _nt else
                f"{_nt} transfer{'s' if _nt != 1 else ''}"
                + (f", {OPT['hitpen'] // 4} hit(s)" if OPT['hitpen'] else ''))
    _opt_sub += f" · free transfer priced at {OPT['ftvalue']:g} pts"
else:
    _opt_sub = 'best legal plan'

if fixmeta.get('k_att') is not None:
    _odds_note += (f" · fixture model k(attack)={fixmeta['k_att']:.2f}, "
                   f"k(opponent defence)={fixmeta['k_def']:.2f}, "
                   f"home ×{fixmeta['home_adv']:.2f}, rmse {fixmeta.get('rmse')}")

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
    page = (html.replace('__STYLE__', theme.style_block())
                .replace('__VALUEBANDS__', band_tables(personal))
                .replace('__SQUADSEC__', SQUAD_SEC if personal else '')
                .replace('__ODDSNOTE__', _odds_note)
                .replace('__TEAMS__', json.dumps(TEAMS, ensure_ascii=False))
                .replace('__TRSRC__', TR_SRC)
                .replace('__MOVES__', _moves_html)
                .replace('__MOVEWIN__', _move_win)
                .replace('__STORIES__', _stories_html)
                .replace('__OPTTOTAL__', f"{OPT['totals'] and round(sum(OPT['totals']) - OPT['hitpen'], 1) or '–'}" if OPT else '–')
                .replace('__OPTSUB__', _opt_sub)
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
