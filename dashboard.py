"""Generate dashboard.html: self-contained FPL model dashboard.

Reuses model.py's scoring (exec'd up to the SCORES-END marker), inlines the
data as JSON, and writes a single static HTML file — servable from any
static host (home server, python -m http.server, nginx).
"""
import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import theme
import version

src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
ns = {}
exec(compile(src, 'model.py', 'exec'), ns)
players, teams = ns['players'], ns['teams']
pos_name = ns['pos_name']

# Last resort only. A hardcoded squad goes stale the first time a transfer is
# made, and silently: the markers keep pointing at players who left.
_FALLBACK_XI = [('Kinsky', 'TOT'), ('Virgil', 'LIV'), ('Calafiori', 'ARS'),
                ('Maguire', 'MUN'), ('B.Fernandes', 'MUN'), ('Szoboszlai', 'LIV'),
                ('Tzolis', 'ARS'), ('E.Le Fée', 'SUN'), ('Haaland', 'MCI'),
                ('João Pedro', 'CHE'), ('Calvert-Lewin', 'LEE')]
_FALLBACK_BENCH = [('Verbruggen', 'BHA'), ('Rodon', 'LEE'), ('Hughes', 'CRY'),
                   ('Diop', 'IPS')]


def _my_squad():
    """The squad as it actually stands, from the last locked gameweek.

    Team id comes from FPL_TEAM_ID or a gitignored my_team.json - not from
    source, because this is a public repository. Falls back to the GW1 squad if
    the API cannot be reached, and says so, because quietly marking the wrong
    eleven is worse than admitting the data is old.
    """
    tid = os.environ.get('FPL_TEAM_ID')
    if not tid and os.path.exists('my_team.json'):
        try:
            tid = str(json.load(open('my_team.json', encoding='utf-8')).get('team_id') or '')
        except Exception:  # noqa: BLE001
            tid = ''
    if not tid:
        print('my squad: no FPL_TEAM_ID - falling back to the GW1 squad')
        return _FALLBACK_XI, _FALLBACK_BENCH, ('Haaland', 'MCI'), ('B.Fernandes', 'MUN')
    try:
        ua = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}
        api = 'https://fantasy.premierleague.com/api'
        boot = ns['d']
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        gw = max((e['id'] for e in boot['events'] if e['deadline_time'] <= now), default=None)
        if not gw:
            raise RuntimeError('no locked gameweek yet')
        req = urllib.request.Request(f'{api}/entry/{tid}/event/{gw}/picks/', headers=ua)
        picks = json.loads(urllib.request.urlopen(req, timeout=25).read())
        by_id = {e['id']: e for e in boot['elements']}
        xi, bench, cap, vice = [], [], None, None
        for pk in sorted(picks['picks'], key=lambda k: k['position']):
            e = by_id.get(pk['element'])
            if not e:
                continue
            key = (e['web_name'], teams[e['team']])
            (xi if pk['position'] <= 11 else bench).append(key)
            if pk.get('is_captain'):
                cap = key
            if pk.get('is_vice_captain'):
                vice = key
        if len(xi) + len(bench) != 15:
            raise RuntimeError(f'got {len(xi) + len(bench)} picks')
        print(f'my squad: GW{gw} picks for entry {tid}')
        return xi, bench, cap, vice
    except Exception as exc:  # noqa: BLE001
        print(f'my squad: live picks unavailable ({exc}) - falling back to GW1')
        return _FALLBACK_XI, _FALLBACK_BENCH, ('Haaland', 'MCI'), ('B.Fernandes', 'MUN')


MY_XI, MY_BENCH, MY_CAPTAIN, MY_VICE = _my_squad()
MY_SQUAD = set(MY_XI) | set(MY_BENCH)


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
                 'g': p['gws'], 'cg': p['chip_gws'], 'tt': p['tot4'], 'pc': pct, 'pl': lik,
                 's': p['sel'], 'mine': pkey(p) in MY_SQUAD, 'xi': pkey(p) in set(MY_XI),
                 'xm': p['xmins'], 'xmg': p['xmins_gws'], 'why': p['src']})
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
for name, club in MY_XI + MY_BENCH:
    p = next(q for q in players if q['name'] == name and teams[q['team']] == club)
    squad_rows.append({'n': name, 't': club, 'p': pos_name[p['pos']],
                       'c': p['price'], 'g': p['gws'], 'tt': p['tot4'],
                       'xi': (name, club) in set(MY_XI)})

html = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fleamarket Analytics</title>
__STYLE__
<div class="wrap">
<div class="brand"><span class="mark">Flea<em>market</em></span><span class="season">2026/27</span></div>
<nav class="tabs">
 <a class="tab" href="#overview">Overview</a>
 <a class="tab" href="#planner">Planner</a>
 <a class="tab" href="#chips">Chips</a>
 <a class="tab" href="#fixtures">Fixtures</a>
 <a class="tab" href="/squads">Manager ↗</a>
 <a class="tab" href="/news">News ↗</a>
</nav>
<nav class="tabs sub" aria-label="Not about fantasy">
 <span class="navlbl">Football</span>
 <a class="tab" href="#teams">Transfer window</a>
 <a class="tab" href="#table">League table</a>
 <a class="tab" href="#week">This week</a>
</nav>

<div class="tabpane" data-tab="overview">
<p class="sub" style="margin-top:16px">Every player scored from last season's Opta rates (xG, xA,
clean sheets, defensive contributions), season expectations, and fixtures. __SUBNOTE__</p>
<div class="tiles">
 <div class="tile urgent"><div class="tl">Deadline</div><div class="tv" id="tile-cd">__DL_TIME__</div><div class="dlwhen" id="tile-dl">__DL_TIME__</div><div class="ts">__DL_GW__</div></div>
 <div class="tile me" id="tile-rank" hidden><div class="tl">Overall rank</div><div class="tv" id="tile-rank-v">–</div><div class="ts" id="tile-rank-s">–</div></div>
 <div class="tile me" id="tile-val" hidden><div class="tl">Team value</div><div class="tv" id="tile-val-v">–</div><div class="ts" id="tile-val-s">all 15 players</div></div>
 <div class="tile me" id="tile-ft" hidden><div class="tl">Free transfers</div><div class="tv" id="tile-ft-v">–</div><div class="ts" id="tile-ft-s">–</div></div>
 <div class="tile me" id="tile-chips" hidden><div class="tl">Chips left</div><div class="tv" id="tile-chips-v">–</div><div class="ts" id="tile-chips-s">–</div></div>
 <div class="tile" id="tile-squad" hidden><div class="tl">Your XI, next 4 GWs</div><div class="tv" id="tile-squad-v">–</div><div class="ts">model projection</div></div>
 <div class="tile" id="tile-link" hidden><div class="tl">No team linked</div><div class="tv" style="font-size:17px"><a href="/squads">Import your team</a></div><div class="ts">rank, value, transfers and chips appear here</div></div>
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
 <h2>Top stories</h2>
 <p class="note">Highest-signal headlines from the last few days, checked against the model's
 assumptions. All of them, plus off-radar finds, on the <a href="/news">News</a> tab.</p>
 __STORIES__
</section>
__SQUADSEC__
</div>

<div class="tabpane" data-tab="planner">
<section class="card">
 <h2>Next 4 gameweeks — the planner</h2>
 <p class="note">Projected points per gameweek against each team's actual fixtures, plus the 4-week total.
 Top 5 keepers, 15 defenders, 20 midfielders, 10 forwards by the selected metric. __RINGNOTE__</p>
 <div class="chips" id="plannerchips"></div>
 <div class="scroll"><table id="planner"></table></div>
</section>
<section class="card">
 <h2>Ownership vs projection</h2>
 <p class="note">The ownership axis is stretched at the low end, so the thinly-owned
 players are readable rather than stacked against the edge.</p>
 <div class="chips" id="chips2"></div>
 <svg id="diff" viewBox="0 0 940 440" role="img" aria-label="Scatter of ownership against expected points per match"></svg>
</section>
</div>

<div class="tabpane" data-tab="chips">
__CHIPPLAN__
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

<div class="tabpane" data-tab="table">
<section class="card">
 <h2>League table</h2>
 <p class="note">Actual Premier League standings, from results so far. Nothing fantasy about it —
 it is here because form and table position are the backdrop everything else is read against.</p>
 <div class="scroll"><table id="ltable"></table></div>
</section>
</div>

<div class="tabpane" data-tab="week">
<section class="card">
 <h2>This week's fixtures <span class="mut" id="weekgw"></span></h2>
 <p class="note">Kick-offs for the coming gameweek, in UK time, with each side's league position.</p>
 <div class="scroll"><table id="wktable"></table></div>
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

<footer>FPL data pulled __PULLED__ UK · refreshed hourly · __ODDSNOTE__
<br><span class="build">build __SHA__ · __SUBJECT__ · generated __BUILT__ UK</span></footer>
</div>
<div class="tip" id="tip"></div>
<script>
const DATA = __DATA__;
const HEAT = __HEAT__;
const SQUAD = __SQUAD__;
const LEAGUE = __LEAGUE__;
const WEEK = __WEEK__;
const CHIPS = __CHIPS__;
const FHBEST = __FHBEST__;
const CHIPEV = __CHIPEV__;
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
       tip = document.getElementById('tip');
const W=940,L=52,R=16,T=14;
const xmax=Math.max(...DATA.map(d=>d.c))+0.4, xmin=3.6;
const ymax=Math.max(...DATA.map(d=>d.x))+0.4, ymin=0;
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
const CHART_MIN=1.8;  // charts hide sub-threshold players (unless in your squad)
const show=(d,f)=>(f==='All'||d.p===f)&&(d.x>=CHART_MIN||d.mine);
function mark(d,i,cx,cy,extra){
 const c=COL[d.p];
 const m = d.p==='GKP'
  ? `<rect x="${cx-4}" y="${cy-4}" width="8" height="8" fill="${c}"${extra||''}/>`
  : `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${c}"${extra||''}/>`;
 return `<g class="dot" data-i="${i}">${d.mine?`<circle cx="${cx}" cy="${cy}" r="8.5" fill="none" stroke="var(--ink)" stroke-width="1.6"/>`:''}${m}<circle cx="${cx}" cy="${cy}" r="13" fill="transparent"/></g>`;
}

// planner: per-GW projections, toggle total vs per-£m
const PLN_N = {GKP:5, DEF:15, MID:20, FWD:10};
let plnMode = 'total';
function drawPlanner(){
 const t=document.getElementById('planner');
 const mark=k=>plnMode===k?'▼ ':'';
 // team rides with the name, the way it reads on a team sheet, which frees the
 // column for ownership - the number you actually weigh a transfer against
 let h=`<tr><th>Player</th><th class="num">${mark('cost')}£m</th><th class="num">Own%</th>`+
  GWL.map(g=>`<th class="num">GW${g}</th>`).join('')+
  `<th class="num">${mark('total')}Total</th><th class="num">${mark('perm')}per £m</th></tr>`;
 const SORT={total:(a,b)=>b.tt-a.tt, perm:(a,b)=>(b.tt/b.c)-(a.tt/a.c),
             cost:(a,b)=>b.c-a.c||b.tt-a.tt, own:(a,b)=>b.s-a.s};
 ['GKP','DEF','MID','FWD'].forEach(p=>{
  const rows=DATA.filter(d=>d.p===p&&d.tt>0).sort(SORT[plnMode]||SORT.total).slice(0,PLN_N[p]);
  h+=`<tr><th colspan="${5+GWL.length}" style="padding-top:12px;color:${COL[p]}">${p}</th></tr>`;
  rows.forEach(d=>{
   const mins=d.xmg?`expected minutes by GW: ${d.xmg.join(' → ')}`:`expected minutes ${d.xm}`;
   h+=`<tr><td title="${esc(mins+' · '+d.why)}">${d.mine?'● ':''}<b>${esc(d.n)}</b>`+
    ` <span class="mut2">${d.t}</span>`+
    `${d.xmg?' <span class="ramp">▲ minutes</span>':''}</td>`+
    `<td class="num">${d.c.toFixed(1)}</td><td class="num">${d.s.toFixed(0)}%</td>`+
    d.g.map(v=>`<td class="num">${v.toFixed(1)}</td>`).join('')+
    `<td class="num"><b>${d.tt.toFixed(1)}</b></td><td class="num">${(d.tt/d.c).toFixed(2)}</td></tr>`;
  });
 });
 t.innerHTML=h;
}
(function(){
 const box=document.getElementById('plannerchips');
 [['total','Top by total xPts'],['perm','Top by xPts per £m'],
  ['cost','By cost'],['own','By ownership']].forEach(([k,lbl],idx)=>{
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
 // sort by SIZE of the move, not by sign: a player 37% of the way to a drop
 // matters as much as one 82% of the way to a rise. Squad order is not relevance
 // order, and leaving this unsorted is why only rises ever showed up here.
 const mine=rows.filter(r=>{const d=DATA.find(x=>x.n===r.n&&x.t===r.t);return d&&(Math.abs(d.pc)>=25||d.pl>=0.3)})
   .map(r=>DATA.find(x=>x.n===r.n&&x.t===r.t))
   .sort((a,b)=>Math.abs(b.pc)-Math.abs(a.pc));
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
// ---- deadline countdown -----------------------------------------------
(function(){
 const el=document.getElementById('tile-cd'), when=Date.parse('__DL_ISO__');
 if(!el||isNaN(when))return;
 const tile=el.closest('.tile');
 // the deadline in the READER's timezone, not the league's. UK time is what
 // every FPL site quotes, so it stays as the small print for cross-reference,
 // but the time you actually have to act by is the one on your own clock.
 const wh=document.getElementById('tile-dl');
 if(wh){
  const d=new Date(when);
  try{
   const f=new Intl.DateTimeFormat(undefined,{weekday:'short',day:'numeric',month:'short',
     hour:'2-digit',minute:'2-digit',hour12:false,timeZoneName:'short'});
   wh.textContent=f.format(d).replace(',','');
  }catch(e){ wh.textContent=d.toLocaleString(); }
 }
 function tick(){
  let ms=when-Date.now();
  if(ms<=0){el.textContent='Deadline passed';tile.classList.remove('urgent');return}
  const h=Math.floor(ms/3600000), m=Math.floor(ms/60000)%60;
  el.textContent = h>=48 ? Math.floor(h/24)+'d '+(h%24)+'h'
                 : h>=1  ? h+'h '+String(m).padStart(2,'0')+'m'
                         : m+'m '+String(Math.floor(ms/1000)%60).padStart(2,'0')+'s';
  tile.classList.toggle('urgent', ms < 6*3600000);
  setTimeout(tick, h>=48?60000:1000);
 }
 tick();
})();

// ---- manager tiles: rank, value, transfers, chips ----------------------
(function(){
 const tid=localStorage.getItem('fpl_team_id');
 const link=document.getElementById('tile-link');
 if(!tid){if(link)link.hidden=false;return}
 const show=(id,v,sub)=>{const t=document.getElementById(id);if(!t)return;
  t.hidden=false;document.getElementById(id+'-v').textContent=v;
  const e=document.getElementById(id+'-s'); if(e&&sub!=null)e.innerHTML=sub;};
 fetch('/api/team/'+encodeURIComponent(tid)).then(r=>r.json()).then(d=>{
  const m=d&&d.summary; if(!m){if(link)link.hidden=false;return}
  if(m.rank!=null){
   // FPL rank is a position, so SMALLER is better: a positive delta is a climb
   const dl=m.rank_delta;
   const arrow = dl==null ? '' :
     dl>0 ? '<span class="up">▲ '+Math.abs(dl).toLocaleString()+'</span>'
          : dl<0 ? '<span class="down">▼ '+Math.abs(dl).toLocaleString()+'</span>'
                 : '<span class="mut">no change</span>';
   show('tile-rank', m.rank.toLocaleString(),
        (arrow?arrow+' ':'')+'<span class="mut">last GW · '+(m.points||0)+' pts</span>');
  }
  if(m.squad_value!=null)
   show('tile-val','£'+m.squad_value.toFixed(1)+'m',
        m.bank?('£'+m.bank.toFixed(1)+'m in the bank'):'all 15 players, nothing banked');
  if(m.free_transfers!=null)
   show('tile-ft', m.free_transfers, m.free_transfers>=5
     ? 'at the cap — use one or lose it' : 'banked, up to 5');
  // null means we could not read them; [] means they are genuinely gone
  if(m.chips===null||m.chips===undefined){
   show('tile-chips','?','could not read chip status');
  }else{
   show('tile-chips', m.chips.length?m.chips.map(c=>c.name).join(' · '):'none',
     m.chips.length?('expire after GW'+m.chips[0].until):'all spent this half');
  }
 }).catch(()=>{if(link)link.hidden=false});
})();

// ---- Chip planner: ranked windows, priced where a squad still means something
(function(){
 const grid=document.getElementById('chipgrid'); if(!grid||!CHIPS.length)return;
 // Beyond about five gameweeks the squad is fiction - it will have turned over
 // several times - so points stop being claimed and the fixture read stands alone.
 const SQUAD_WEEKS=5, SHOW=5;
 const MIN={GKP:1,DEF:3,MID:2,FWD:1}, MAX={GKP:1,DEF:5,MID:5,FWD:3};
 const META={tc:{name:'Triple Captain'},bb:{name:'Bench Boost'},fh:{name:'Free Hit'}};

 function bestXI(sq,i){
  const val=r=>(r.cg&&r.cg[i]!=null)?r.cg[i]:0;
  const by={GKP:[],DEF:[],MID:[],FWD:[]};
  sq.forEach(r=>(by[r.p]||by.MID).push(r));
  Object.values(by).forEach(a=>a.sort((x,y)=>val(y)-val(x)));
  const xi=[]; Object.keys(MIN).forEach(k=>xi.push(...by[k].slice(0,MIN[k])));
  const rest=sq.filter(r=>!xi.includes(r)).sort((x,y)=>val(y)-val(x));
  while(xi.length<11&&rest.length){
   const nx=rest.shift();
   if(xi.filter(z=>z.p===nx.p).length<MAX[nx.p])xi.push(nx);
  }
  const bench=sq.filter(r=>!xi.includes(r));
  return {tot:xi.reduce((a,r)=>a+val(r),0), cap:xi.reduce((m,r)=>Math.max(m,val(r)),0),
          benchSum:bench.reduce((a,r)=>a+val(r),0), bench:bench,
          capName:(xi.slice().sort((a,b)=>val(b)-val(a))[0]||{}).n};
 }

 // points, but only inside the window where a squad is still a real object
 function price(sq){
  const out={};
  CHIPEV.forEach((ev,i)=>{
   if(!sq||i>=SQUAD_WEEKS)return;
   const b=bestXI(sq,i), fh=FHBEST[i];
   out[ev]={tc:b.cap, capName:b.capName, bb:b.benchSum,
            fh:fh?Math.max(fh.total-(b.tot+b.cap),0):null,
            fhcap:fh?fh.cap:null, own:b.tot+b.cap,
            weak:b.bench.filter(r=>(r.xm||0)<45).map(r=>r.n)};
  });
  return out;
 }

 function reason(k,r,pt){
  if(k==='tc'){
   const f=r.tcfix;
   if(!f)return 'no fixture priced';
   return `${f.team} ${f.home?'at home to':'away at'} ${f.opp} · ${f.gf.toFixed(2)} xG`
        + (pt&&pt.capName?` · your best is ${pt.capName}`:'');
  }
  if(k==='bb'){
   const bits=[];
   if(r.doubles.length)bits.push(r.doubles.length+' double'+(r.doubles.length>1?'s':''));
   if(r.blanks.length)bits.push(r.blanks.length+' blank'+(r.blanks.length>1?'s':''));
   bits.push('board average ×'+r.bbmean.toFixed(2));
   if(pt&&pt.weak&&pt.weak.length)bits.push('but '+pt.weak.join(', ')+' may not start');
   return bits.join(' · ');
  }
  const bits=[];
  if(r.template!=null&&r.field!=null)
   bits.push(`template ${r.template.toFixed(1)} → best XI ${r.field.toFixed(1)}`);
  if(r.weak&&r.weak.length)
   bits.push('template hurt by '+r.weak.map(w=>`${w.n} (${w.sel}% owned)`).join(', '));
  if(r.blanks.length)bits.push(r.blanks.length+' blank'+(r.blanks.length>1?'s':''));
  return bits.join(' · ')||'no strong edge';
 }

 function render(have,priced,note){
  const picks={};
  grid.innerHTML=Object.keys(META).filter(k=>have.includes(k.toUpperCase())).map(k=>{
   const all=[...CHIPS].sort((a,b)=>b[k]-a[k]);
   const rank=all.slice(0,SHOW);
   const top=rank[0], tp=priced[top.gw];
   picks[k]=top.gw;
   // if the whole window scores the same, the ranking is noise and should say so
   const span=all[0][k]-all[all.length-1][k];
   const base=Math.abs(all[0][k])||1;
   const weak=(span/base)<0.08;
   // Free Hit is measured against the average manager, not against your own
   // fifteen, so it carries a points figure in every week rather than only the
   // near ones. TC and BB still need your squad.
   const own=tp&&tp[k]!=null?tp[k]:null;
   const gain = k==='fh'
    ? `<div class="gain">+${top.fh.toFixed(1)} pts <span class="vs">vs the template</span></div>`
      + (own!=null?`<div class="ts">+${own.toFixed(1)} against your own XI</div>`:'')
    : (own!=null
       ? `<div class="gain">+${own.toFixed(1)} pts</div>`
       : `<div class="gain unpriced">beyond the priced window</div>`);
   // The list is ordered by FIXTURES, which is the planner's job, but the points
   // are the better estimate wherever they exist. When the two disagree - and
   // for a chip like Bench Boost, whose fixture spread is noise, they routinely
   // will - say so rather than leaving a headline that its own runner-up beats.
   const pricedRows=CHIPS.filter(r=>priced[r.gw]&&priced[r.gw][k]!=null)
     .sort((a,b)=>priced[b.gw][k]-priced[a.gw][k]);
   const bestPriced=pricedRows[0];
   const disagrees=k!=='fh'&&bestPriced&&(!tp||tp[k]==null||bestPriced.gw!==top.gw);
   const bestLine=disagrees
    ? `<div class="ts bestp">On points alone the pick is <b>GW${bestPriced.gw}</b> at `
      + `+${priced[bestPriced.gw][k].toFixed(1)} — best of the weeks we can price.</div>`
    : '';
   const alts=rank.slice(1).map(r=>{
    const p=priced[r.gw];
    const val = k==='fh' ? `<b>+${r.fh.toFixed(1)}</b>`
      : (p&&p[k]!=null?`<b>+${p[k].toFixed(1)}</b>`:'<span class="mut2">fixtures only</span>');
    return `<li><span class="agw">GW${r.gw}</span> ${val}`+
           `<span class="why">${esc(reason(k,r,p))}</span></li>`;
   }).join('');
   const flag=weak
    ? `<div class="ts warn">Fixtures barely separate these weeks (${span.toFixed(2)} across ten).`
      + ` Treat the order as noise — for this chip the real signal is your own squad,`
      + ` and the doubles and blanks that are not scheduled yet.</div>`
    : '';
   return `<div class="chipcard"><div class="tl">${META[k].name}</div>`+
    `<div class="tv">GW${top.gw}</div>${gain}`+
    `<div class="ts">${esc(reason(k,top,tp))}</div>${bestLine}${flag}`+
    `<ol class="alts">${alts}</ol></div>`;
  }).join('')||'<p class="note">No chips left in this half of the season.</p>';

  // one chip per gameweek: if two headline picks collide, say so
  const clash={};
  Object.entries(picks).forEach(([k,g])=>(clash[g]=clash[g]||[]).push(META[k].name));
  const dup=Object.entries(clash).filter(([,v])=>v.length>1);
  if(dup.length){
   const w=document.createElement('p');
   w.className='note warn';
   w.textContent=dup.map(([g,v])=>
    `${v.join(' and ')} both point at GW${g}, and only one chip can be played in a gameweek — `+
    `take the second-choice week for whichever gains less.`).join(' ');
   grid.parentNode.insertBefore(w, grid.nextSibling);
  }

  const t=document.getElementById('chiptable');
  if(t)t.innerHTML='<tr><th class="num">GW</th><th>Doubles</th><th>Blanks</th>'+
   '<th class="num">TC ceiling</th><th class="num">Board</th><th class="num">FH vs template</th>'+
   '<th class="num">Your XI</th><th class="num">TC</th><th class="num">BB</th><th class="num">FH</th></tr>'+
   CHIPS.map(r=>{
    const p=priced[r.gw]||{};
    const n=v=>v==null?'<span class="mut2">—</span>':'+'+v.toFixed(1);
    return `<tr><td class="num"><b>${r.gw}</b></td><td>${r.doubles.join(', ')||'—'}</td>`+
     `<td>${r.blanks.join(', ')||'—'}</td>`+
     `<td class="num">${r.tc.toFixed(2)}</td><td class="num">${r.bbmean.toFixed(2)}</td>`+
     `<td class="num">${r.fh.toFixed(1)}</td>`+
     `<td class="num">${p.own!=null?p.own.toFixed(1):'<span class="mut2">—</span>'}</td>`+
     `<td class="num">${n(p.tc)}</td><td class="num">${n(p.bb)}</td><td class="num">${n(p.fh)}</td></tr>`;
   }).join('');
  const nel=document.getElementById('chipnote');
  if(nel)nel.textContent=note||('Points shown for the next '+SQUAD_WEEKS+
    ' gameweeks only — beyond that your squad will have turned over and the fixture read is all that survives.');
 }

 function squadFromLines(lines){
  const idx=new Map(DATA.map(d=>[d.n+'|'+d.t,d]));
  return lines.map(l=>{const q=l.trim().split(' '),t=q.pop();return idx.get(q.join(' ')+'|'+t)})
              .filter(Boolean);
 }
 const ALL=['TC','BB','FH'];
 const tid=localStorage.getItem('fpl_team_id');
 if(!tid){
  let sq=null;
  try{const sv=localStorage.getItem('fpl_my_squad'); if(sv)sq=squadFromLines(JSON.parse(sv));}catch(e){}
  return render(ALL, sq&&sq.length>=15?price(sq):{},
    sq&&sq.length>=15?null:'Link your team on the Manager page to price these in points — the rankings below are fixtures only.');
 }
 fetch('/api/team/'+encodeURIComponent(tid)).then(r=>r.json()).then(d=>{
  const sq=squadFromLines((d&&d.lines)||[]);
  const c=d&&d.summary?d.summary.chips:undefined;
  render(c==null?ALL:c.map(x=>x.name), sq.length>=15?price(sq):{},
         sq.length>=15?null:'Squad unavailable — rankings are fixtures only.');
 }).catch(()=>render(ALL,{},'Squad unavailable — rankings are fixtures only.'));
})();

// ---- Football: league table and the week's kick-offs -------------------
(function(){
 const lt=document.getElementById('ltable');
 if(lt&&LEAGUE.length){
  const cls=r=>r.pos<=4?'ucl':r.pos<=6?'uel':r.pos>=18?'rel':'';
  lt.innerHTML='<tr><th class="num">#</th><th>Club</th><th class="num">P</th><th class="num">W</th>'+
   '<th class="num">D</th><th class="num">L</th><th class="num">GF</th><th class="num">GA</th>'+
   '<th class="num">GD</th><th class="num">Pts</th><th>Form</th></tr>'+
   LEAGUE.map(r=>`<tr class="${cls(r)}"><td class="num">${r.pos}</td><td><b>${r.team}</b></td>`+
    [r.p,r.w,r.d,r.l,r.gf,r.ga].map(v=>`<td class="num">${v}</td>`).join('')+
    `<td class="num">${r.gd>0?'+':''}${r.gd}</td><td class="num"><b>${r.pts}</b></td>`+
    `<td>${[...r.form].map(c=>`<span class="frm f${c}">${c}</span>`).join('')}</td></tr>`).join('');
 }
 const wt=document.getElementById('wktable');
 if(wt&&WEEK.length){
  const g=document.getElementById('weekgw'); if(g)g.textContent='GW'+GWL[0];
  wt.innerHTML='<tr><th>Kick-off</th><th class="num"></th><th>Home</th><th class="num"></th>'+
   '<th>Away</th><th class="num"></th></tr>'+
   WEEK.map(f=>`<tr><td>${f.when||'TBC'}</td><td class="num mut2">${f.hp||''}</td>`+
    `<td><b>${f.h}</b></td><td class="num">${f.done?'<b>'+f.score+'</b>':'v'}</td>`+
    `<td><b>${f.a}</b></td><td class="num mut2">${f.ap||''}</td></tr>`).join('');
 }
})();

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
   // must be `mine`: that is the flag the charts, planner and tooltips read.
   // Setting `v4` here meant nothing anywhere consumed it, so a reader's own
   // squad was never marked on the public page at all.
   if(i!=null){DATA[i].mine=true; rows.push(DATA[i]);}
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

_BUILD = version.write_stamp()
_BUILD['sha'] = _BUILD['sha'][:7] if _BUILD['sha'] != 'unknown' else 'unknown'
if version.dirty():
    _BUILD['sha'] += '+dirty'
_BUILT_UK = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%a %d %b %H:%M')


def _esc(t):
    return (t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


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

def league_table(fixtures, team_name):
    """Actual Premier League standings from finished results.

    Not fantasy, which is why it lives under Football - but form and position
    are the backdrop every projection is read against, and the app had no way
    to answer 'who is actually any good this season'.
    """
    tbl = {t: dict(team=t, p=0, w=0, d=0, l=0, gf=0, ga=0, pts=0, form='')
           for t in team_name.values()}
    for f in sorted((x for x in fixtures if x.get('finished')),
                    key=lambda x: x.get('event') or 0):
        hs, as_ = f.get('team_h_score'), f.get('team_a_score')
        if hs is None or as_ is None:
            continue
        h, a = team_name[f['team_h']], team_name[f['team_a']]
        for side, gf, ga in ((h, hs, as_), (a, as_, hs)):
            r = tbl[side]
            r['p'] += 1
            r['gf'] += gf
            r['ga'] += ga
            res = 'W' if gf > ga else 'D' if gf == ga else 'L'
            r[res.lower()] += 1
            r['pts'] += 3 if res == 'W' else 1 if res == 'D' else 0
            r['form'] = (r['form'] + res)[-5:]
    rows = sorted(tbl.values(), key=lambda r: (-r['pts'], -(r['gf'] - r['ga']), -r['gf'], r['team']))
    for i, r in enumerate(rows, 1):
        r['pos'] = i
        r['gd'] = r['gf'] - r['ga']
    return rows


def week_fixtures(fixtures, team_name, event, table):
    """Kick-offs for one gameweek, UK time, with each side's league position."""
    pos = {r['team']: r['pos'] for r in table}
    out = []
    for f in sorted((x for x in fixtures if x.get('event') == event),
                    key=lambda x: (x.get('kickoff_time') or '', x['id'])):
        ko = f.get('kickoff_time')
        when = ''
        if ko:
            when = (datetime.strptime(ko, '%Y-%m-%dT%H:%M:%SZ')
                    + timedelta(hours=1)).strftime('%a %d %b · %H:%M')
        h, a = team_name[f['team_h']], team_name[f['team_a']]
        out.append({'h': h, 'a': a, 'hp': pos.get(h), 'ap': pos.get(a),
                    'when': when, 'done': bool(f.get('finished')),
                    'score': (f"{f['team_h_score']}-{f['team_a_score']}"
                              if f.get('team_h_score') is not None else '')})
    return out


def template_xi(pts, gw_events):
    """What the average manager is expected to score, week by week.

    Aggregate club ownership was the wrong measure and produced nonsense.
    Tottenham cleared the "heavily owned" bar on 74%, of which 17.9% is Dubravka
    - a backup keeper projected at zero - so a fixture against them was reported
    as two owned attacks cancelling out when Spurs' entire template exposure is
    1.57 points. Brighton's 80% is three cheap defenders and two goalkeepers.
    Arsenal's 213% is Calafiori, Raya and Gabriel, and worth 8.16.

    So the template is built the way a squad is: the most-owned players that form
    a legal XI, captained on the best of them. That is directly comparable with
    the Free Hit ceiling, and a player nobody starts contributes nothing to it.
    """
    QUOTA = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}
    ranked = sorted(pts, key=lambda q: -q['sel'])
    out = []
    for i, ev in enumerate(gw_events):
        xi, per_pos, per_club = [], {1: 0, 2: 0, 3: 0, 4: 0}, {}
        for q in ranked:
            if len(xi) >= 11:
                break
            lo, hi = QUOTA[q['pos']]
            if per_pos[q['pos']] >= hi or per_club.get(q['team'], 0) >= 3:
                continue
            # keep room for the minimum of every position still unfilled
            need = sum(max(QUOTA[k][0] - per_pos[k], 0) for k in QUOTA if k != q['pos'])
            if 11 - len(xi) - 1 < need:
                continue
            xi.append(q)
            per_pos[q['pos']] += 1
            per_club[q['team']] = per_club.get(q['team'], 0) + 1
        val = lambda q: q['chip_gws'][i] if i < len(q['chip_gws']) else 0.0
        cap = max((val(q) for q in xi), default=0.0)
        # who in the template is having a bad week, judged against their own
        # normal level and weighted by how many managers actually hold them
        weak = sorted(
            ({'n': q['name'], 't': teams[q['team']], 'sel': round(q['sel'], 1),
              'cost': round((sum(q['chip_gws']) / len(q['chip_gws']) - val(q))
                            * q['sel'] / 100, 2)}
             for q in xi if q['chip_gws']),
            key=lambda r: -r['cost'])[:3]
        out.append({'gw': ev, 'total': round(sum(val(q) for q in xi) + cap, 2),
                    'weak': [w for w in weak if w['cost'] > 0.01]})
    return out


def free_hit_ceiling(pts, gw_events, budget=100.0):
    """Best legal fifteen, week by week, scored as an XI with a captain.

    A Free Hit is worth the difference between the team you have and the team
    you could field for one week, so the honest number needs the second half of
    that comparison actually solved rather than guessed. One small MILP per
    gameweek: 2/5/5/3, at most three per club, inside the budget, best eleven
    from the fifteen, captain doubled - the same rules the chip is played under.
    """
    import pulp
    pool = [q for q in pts if q['price'] > 0 and sum(q['chip_gws']) > 0]
    out = []
    for i, ev in enumerate(gw_events):
        xp = [q['chip_gws'][i] if i < len(q['chip_gws']) else 0.0 for q in pool]
        prob = pulp.LpProblem(f'fh{ev}', pulp.LpMaximize)
        sq = [pulp.LpVariable(f's{j}', cat='Binary') for j in range(len(pool))]
        xi = [pulp.LpVariable(f'x{j}', cat='Binary') for j in range(len(pool))]
        cp = [pulp.LpVariable(f'c{j}', cat='Binary') for j in range(len(pool))]
        prob += pulp.lpSum(xi[j] * xp[j] + cp[j] * xp[j] for j in range(len(pool)))
        prob += pulp.lpSum(sq) == 15
        prob += pulp.lpSum(xi) == 11
        prob += pulp.lpSum(cp) == 1
        prob += pulp.lpSum(sq[j] * pool[j]['price'] for j in range(len(pool))) <= budget
        for j in range(len(pool)):
            prob += xi[j] <= sq[j]
            prob += cp[j] <= xi[j]
        for code, quota, lo, hi in ((1, 2, 1, 1), (2, 5, 3, 5), (3, 5, 2, 5), (4, 3, 1, 3)):
            idx = [j for j in range(len(pool)) if pool[j]['pos'] == code]
            prob += pulp.lpSum(sq[j] for j in idx) == quota
            prob += pulp.lpSum(xi[j] for j in idx) >= lo
            prob += pulp.lpSum(xi[j] for j in idx) <= hi
        clubs = {}
        for j in range(len(pool)):
            clubs.setdefault(pool[j]['team'], []).append(j)
        for idx in clubs.values():
            prob += pulp.lpSum(sq[j] for j in idx) <= 3
        prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=20))
        if pulp.LpStatus[prob.status] != 'Optimal':
            out.append(None)
            continue
        chosen = [j for j in range(len(pool)) if xi[j].value() and xi[j].value() > 0.5]
        capj = next((j for j in range(len(pool)) if cp[j].value() and cp[j].value() > 0.5), None)
        out.append({'gw': ev,
                    'total': round(sum(xp[j] for j in chosen)
                                   + (xp[capj] if capj is not None else 0), 2),
                    'cap': pool[capj]['name'] if capj is not None else None})
    return out


def chip_plan(fixtures, team_name, fixmap, elements, from_gw, fh_rows=(), tpl_rows=(),
              half_end=19, horizon=10):
    """Score every remaining gameweek in this half, per chip, on FIXTURES.

    Planning a squad fifteen weeks out is fiction - the team will have changed
    several times over. What survives that long is the CALENDAR, so this ranks
    windows rather than projecting a squad into them. Near-term weeks get a
    points figure against the actual squad on top (see the page script); beyond
    that the fixture read is the honest limit of what can be said.

    Each chip is scored on what it actually needs:

      Triple Captain - the biggest single ceiling on the board. That is absolute
        expected goals, not goals relative to a team's own average: a strong
        side at home to a weak defence, which is what a strength differential
        plus home advantage produces.
      Bench Boost    - a week the whole board plays well, since the chip pays
        only if all fifteen return. Doubles dominate once they exist.
      Free Hit       - a week that hurts the template and rewards what nobody
        owns. Scored as the gap between the fixtures available to lightly-owned
        clubs and the fixtures the heavily-owned ones are stuck with, plus the
        clashes that put two popular attacks against each other.
    """
    by_gw = {}
    for f in fixtures:
        if f.get('event'):
            by_gw.setdefault(f['event'], []).append(f)
    fh_by_gw = {r['gw']: r for r in (fh_rows or []) if r}
    tpl_by_gw = {r['gw']: r for r in (tpl_rows or []) if r}

    gws = [g for g in sorted(by_gw) if from_gw <= g <= half_end][:horizon]
    rows = []
    for g in gws:
        fx = by_gw[g]
        played = {}
        for f in fx:
            for t in (f['team_h'], f['team_a']):
                played[t] = played.get(t, 0) + 1
        doubles = sorted(team_name[t] for t, n in played.items() if n > 1)
        blanks = sorted(team_name[t] for t in team_name if not played.get(t))

        cells = []          # (club, opp, home, af, gf)
        for f in fx:
            for t, opp, home in ((f['team_h'], f['team_a'], 1), (f['team_a'], f['team_h'], 0)):
                c = team_name[t]
                v = (fixmap.get(c) or {}).get(str(g)) or {}
                if v.get('af') is None:
                    continue
                cells.append((c, team_name[opp], home, v['af'], v.get('gf') or 0.0))

        # --- Triple Captain: the biggest absolute ceiling available ----------
        tc_best = max(cells, key=lambda r: r[4]) if cells else None

        # --- Bench Boost: does the whole board play well? --------------------
        # NOT the mean of af: af is each club's goals relative to its OWN average,
        # so averaging it over all twenty clubs gives 1.00 every single week and
        # ranks nothing. Absolute expected goals does vary, and a high-scoring
        # week is one where fringe players return too.
        bb_mean = sum(r[4] for r in cells) / len(cells) if cells else 0.0
        # a bench only boosts if it plays, so weeks with brutal fixtures for the
        # cheap end are worse than the mean alone suggests
        rough = sum(1 for r in cells if r[3] < 0.8)
        bb = round(bb_mean + 1.2 * len(doubles) - 0.5 * len(blanks) - 0.02 * rough, 3)

        # --- Free Hit: what the field can reach minus what the template gets -
        # Both sides are now POINTS, from a real XI, so the number means
        # something: how far ahead of the average manager one week of freedom
        # puts you. Ownership sums told us Spurs were a template club on the
        # strength of a backup keeper.
        f_row = fh_by_gw.get(g) or {}
        t_row = tpl_by_gw.get(g) or {}
        fh = round((f_row.get('total') or 0) - (t_row.get('total') or 0), 2)

        rows.append({
            'gw': g, 'doubles': doubles, 'blanks': blanks,
            'tc': round(tc_best[4], 3) if tc_best else 0.0,
            'tcfix': ({'team': tc_best[0], 'opp': tc_best[1], 'home': tc_best[2],
                       'gf': round(tc_best[4], 2)} if tc_best else None),
            'bb': bb, 'bbmean': round(bb_mean, 3), 'rough': rough,
            'fh': fh, 'fhedge': fh,
            'template': t_row.get('total'), 'field': f_row.get('total'),
            'weak': t_row.get('weak') or [],
        })
    return rows


_fx_all = json.load(open('fixtures.json', encoding='utf-8'))
LEAGUE = league_table(_fx_all, teams)
WEEK = week_fixtures(_fx_all, teams, gw_labels[0], LEAGUE)
CHIP_EVENTS = ns['CHIP_EVENTS']
try:
    FHBEST = free_hit_ceiling(pts, CHIP_EVENTS)
    print('free hit ceiling: %d/%d gameweeks solved'
          % (sum(1 for r in FHBEST if r), len(FHBEST)))
except Exception as _fhe:  # noqa: BLE001 - chips degrade, page still builds
    print('free hit ceiling skipped:', _fhe)
    FHBEST = []
TEMPLATE = template_xi(pts, CHIP_EVENTS)
CHIPS = chip_plan(_fx_all, teams, FIXMAP, ns['d']['elements'], gw_labels[0],
                  fh_rows=FHBEST, tpl_rows=TEMPLATE)

_ev = next(e for e in ns['d']['events'] if e['id'] == gw_labels[0])
_dl = datetime.strptime(_ev['deadline_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=1)  # UK summer time
tile_deadline = _dl.strftime('%a %d %b, %H:%M')
tile_dl_gw = f"GW{gw_labels[0]} · {_dl.strftime('%H:%M')} UK"
# the raw instant, so the tile can count down live rather than print a date the
# reader then has to subtract today from
_dl_iso = _ev['deadline_time'].replace('Z', '+00:00')
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
    # "since the deadline" is the window a manager actually thinks in: a six-hour
    # slice cuts across the middle of a gameweek and answers a question nobody
    # asked. Cap it so an early-season long gap does not swallow the whole run.
    _prev_dl = max((e['deadline_time'] for e in ns['d']['events']
                    if e['deadline_time'] <= datetime.now(timezone.utc)
                    .strftime('%Y-%m-%dT%H:%M:%SZ')), default=None)
    _win_h = 6.0
    _cur_gw = next((e['id'] for e in ns['d']['events']
                    if e['deadline_time'] == _prev_dl), None)
    if _prev_dl:
        _since = (datetime.now(timezone.utc)
                  - datetime.strptime(_prev_dl, '%Y-%m-%dT%H:%M:%SZ')
                  .replace(tzinfo=timezone.utc)).total_seconds() / 3600
        _win_h = max(min(_since, 200.0), 3.0)
    _ris, _fal, _meta = _mom.recent_moves(_els, teams, hours=_win_h)

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
        _move_win = (f"since the GW{_cur_gw} deadline" if _prev_dl
                     else f"last {_meta['hours']:.0f}h")
    else:
        _moves_html = ("<p class='note'>Collecting baseline — movement appears once we have "
                       "a few hours of snapshots and the gameweek opens.</p>")
        _move_win = f"{_meta.get('snapshots', 0)} snapshots so far"
except Exception as _e:
    _moves_html = f"<p class='note'>Movements unavailable ({_html.escape(str(_e)[:60])}).</p>"
    _move_win = ''
# Movements belong with the rest of "what changed this week", which is the News
# page - the Overview is for the reader's own team. Published as a fragment so
# app.py can render it without recomputing the snapshot history.
try:
    with open('movements.html', 'w', encoding='utf-8') as _f:
        _f.write("<!--" + _move_win + "-->" + chr(10) + _moves_html)
except Exception as _e2:  # noqa: BLE001
    print('movements fragment skipped:', _e2)

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


CHIP_META = {
    'tc': ('TC', 'Triple Captain', 'the single best attacking fixture on the board'),
    'bb': ('BB', 'Bench Boost', 'every one of your fifteen playing a good fixture'),
    'fh': ('FH', 'Free Hit', 'a week that hurts most squads and rewards a few'),
}


def chip_html(rows):
    """Ranked windows per chip, with a recommendation and a runner-up."""
    if not rows:
        return ('<section class="card"><h2>Chips</h2><p class="note">'
                'No gameweeks left in this half to plan against.</p></section>')
    return (
        '<section class="card"><h2>Chip planner '
        f'<span class="mut">GW{rows[0]["gw"]}–{rows[-1]["gw"]}</span></h2>'
        '<p class="note" id="chipnote"></p>'
        '<div class="chipgrid" id="chipgrid"></div></section>'
        '<section class="card"><h2>Every gameweek, priced</h2>'
        '<p class="note">Every week, both readings side by side: the fixture scores that rank the '
        'windows, then the points they are worth against your current squad where that can still '
        'be said. Blanks and doubles are not scheduled this far out yet, and they move these '
        'numbers more than fixture quality does — expect the back half to shift.</p>'
        '<div class="scroll"><table id="chiptable"></table></div></section>')


def emit(path, personal):
    # public copy strips squad markers entirely (no rings, labels, table, or
    # flags in the embedded JSON) so nothing about our team leaks pre-deadline
    dat = data if personal else [{**r, 'mine': False, 'xi': False} for r in data]
    page = (html.replace('__STYLE__', theme.style_block())
                .replace('__CHIPPLAN__', chip_html(CHIPS))
                .replace('__SQUADSEC__', SQUAD_SEC if personal else '')
                .replace('__ODDSNOTE__', _odds_note)
                .replace('__TEAMS__', json.dumps(TEAMS, ensure_ascii=False))
                .replace('__TRSRC__', TR_SRC)

                .replace('__STORIES__', _stories_html)
                .replace('__PULLED__', (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%a %d %b %H:%M'))
                .replace('__SHA__', _BUILD['sha'])
                .replace('__SUBJECT__', _esc(_BUILD['subject'] or 'no subject')[:68])
                .replace('__BUILT__', _BUILT_UK)
                .replace('__DL_TIME__', tile_deadline).replace('__DL_GW__', tile_dl_gw)
                .replace('__DL_ISO__', _dl_iso)
                .replace('__SUBNOTE__', 'Squad v5 marked with rings. ' if personal else '')
                .replace('__RINGNOTE__', 'Ringed dots / ● = our squad. ' if personal else '')
                .replace('__GWL__', json.dumps(gw_labels))
                .replace('__DATA__', json.dumps(dat, ensure_ascii=False))
                .replace('__HEAT__', json.dumps(heat, ensure_ascii=False))
                .replace('__SQUAD__', json.dumps(squad_rows if personal else [], ensure_ascii=False))
                .replace('__LEAGUE__', json.dumps(LEAGUE, ensure_ascii=False))
                .replace('__WEEK__', json.dumps(WEEK, ensure_ascii=False))
                .replace('__CHIPS__', json.dumps(CHIPS, ensure_ascii=False))
                .replace('__FHBEST__', json.dumps(FHBEST, ensure_ascii=False))
                .replace('__CHIPEV__', json.dumps(CHIP_EVENTS)))
    open(path, 'w', encoding='utf-8').write(page)


emit('dashboard.html', False)      # public: general analysis only (served by app.py)
emit('my_dashboard.html', True)    # personal: includes the submitted squad (local viewing only)
print(f'dashboard.html (public) + my_dashboard.html (personal): {len(data)} players, {len(heat)} teams')
