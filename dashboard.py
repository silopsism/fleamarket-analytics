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

V4_XI = ['Kinsky', 'Guéhi', 'Mosquera', 'Maguire', 'B.Fernandes',
         'Szoboszlai', 'Mbeumo', 'E.Le Fée', 'Haaland', 'João Pedro', 'Brobbey']
V4_BENCH = ['Verbruggen', 'Davis', 'van Ewijk', 'Hughes']
V4 = set(V4_XI) | set(V4_BENCH)

pts = [p for p in players if p['xpts'] >= 1.8 or p['name'] in V4]
data = [{'n': p['name'], 't': teams[p['team']], 'p': pos_name[p['pos']],
         'c': p['price'], 'x': round(p['xpts'], 2), 's': p['sel'],
         'v4': p['name'] in V4, 'xi': p['name'] in V4_XI} for p in pts]

fx = json.load(open('fixtures.json', encoding='utf-8'))
runs = defaultdict(dict)
for f in fx:
    if f['event'] and f['event'] <= 6:
        runs[teams[f['team_h']]][f['event']] = {'o': teams[f['team_a']], 'd': f['team_h_difficulty'], 'h': 1}
        runs[teams[f['team_a']]][f['event']] = {'o': teams[f['team_h']], 'd': f['team_a_difficulty'], 'h': 0}
order = sorted(runs, key=lambda t: sum(g['d'] for g in runs[t].values()))
heat = [{'team': t, 'gws': [runs[t].get(gw) for gw in range(1, 7)]} for t in order]

squad_rows = []
for name in V4_XI + V4_BENCH:
    p = next(q for q in players if q['name'] == name)
    squad_rows.append({'n': name, 't': teams[p['team']], 'p': pos_name[p['pos']],
                       'c': p['price'], 'x': round(p['xpts'], 2),
                       'xi': name in V4_XI})

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
body{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:28px 20px 60px}
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
.chip[aria-pressed="true"]{color:var(--ink);border-color:var(--axis)}
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
</style>
<div class="wrap">
<header>
 <div class="eyebrow">Fleamarket Bargains · 2026/27 · Phase 1 model</div>
 <h1>Fleamarket Analytics</h1>
 <p class="sub">Every player scored from last season's Opta rates (xG, xA, clean sheets,
 defensive contributions), adjusted for opening fixtures. Squad v4 marked with rings.
 Deadline: Fri 21 Aug, 18:30 UK.</p>
</header>

<section class="card">
 <h2>Value map — price vs expected points</h2>
 <p class="note">xPts per match from prior-season rates, GW1–4 fixture-adjusted. Ringed dots = our squad. Hover or tap any dot. Goalkeepers drawn as gray squares.</p>
 <div class="chips" id="chips"></div>
 <svg id="scat" viewBox="0 0 940 520" role="img" aria-label="Scatter plot of player price against expected points per match"></svg>
</section>

<section class="card">
 <h2>Opening fixtures — GW1–6</h2>
 <p class="note">Sorted easiest run first. Darker = harder (FPL difficulty rating). Uppercase = home.</p>
 <div class="scroll hm"><table id="heatmap"></table></div>
</section>

<section class="card">
 <h2>Squad v4 — £100.0m</h2>
 <p class="note">Starting XI then bench, with each player's model score.</p>
 <div class="scroll"><table id="squad"><thead><tr>
 <th>Player</th><th>Team</th><th>Pos</th><th class="num">£m</th><th class="num">xPts/match</th><th>Role</th>
 </tr></thead><tbody></tbody></table></div>
</section>

<footer>Phase 1 model: prior-season rates only — it can't yet see role changes,
transfers between clubs, or minutes risk, so treat scores as a value lens, not an
oracle. Regenerate with <code>python dashboard.py</code> after each data pull.</footer>
</div>
<div class="tip" id="tip"></div>
<script>
const DATA = __DATA__;
const HEAT = __HEAT__;
const SQUAD = __SQUAD__;
const COL = {DEF:'var(--def)',MID:'var(--mid)',FWD:'var(--fwd)',GKP:'var(--gkp)'};
const on = {GKP:true,DEF:true,MID:true,FWD:true};
const svg = document.getElementById('scat'), tip = document.getElementById('tip');
const W=940,H=520,L=52,R=16,T=14,B=44;
const xmax=Math.max(...DATA.map(d=>d.c))+0.4, xmin=3.6;
const ymax=Math.max(...DATA.map(d=>d.x))+0.4, ymin=0;
const X=v=>L+(v-xmin)/(xmax-xmin)*(W-L-R), Y=v=>H-B-(v-ymin)/(ymax-ymin)*(H-T-B);
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function draw(){
 let g='';
 for(let p=Math.ceil(ymin);p<=ymax;p++) g+=`<line x1="${L}" x2="${W-R}" y1="${Y(p)}" y2="${Y(p)}" stroke="var(--grid)"/>`+
  `<text x="${L-8}" y="${Y(p)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${p}</text>`;
 for(let c=4;c<=xmax;c+=1) g+=`<text x="${X(c)}" y="${H-B+18}" text-anchor="middle" font-size="11" fill="var(--muted)">£${c}</text>`;
 g+=`<line x1="${L}" x2="${W-R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/>`;
 g+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" font-size="11.5" fill="var(--ink2)">Price (£m)</text>`;
 g+=`<text x="14" y="${(T+H-B)/2}" font-size="11.5" fill="var(--ink2)" transform="rotate(-90 14 ${(T+H-B)/2})" text-anchor="middle">xPts per match</text>`;
 DATA.forEach((d,i)=>{
  if(!on[d.p])return;
  const cx=X(d.c),cy=Y(d.x),c=COL[d.p];
  const mark = d.p==='GKP'
   ? `<rect x="${cx-4}" y="${cy-4}" width="8" height="8" fill="${c}"/>`
   : `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${c}"/>`;
  g+=`<g class="dot" data-i="${i}">${d.v4?`<circle cx="${cx}" cy="${cy}" r="8.5" fill="none" stroke="var(--ink)" stroke-width="1.6"/>`:''}${mark}<circle cx="${cx}" cy="${cy}" r="13" fill="transparent"/></g>`;
  if(d.v4&&d.xi&&['Haaland','B.Fernandes','Verbruggen','Guéhi','E.Le Fée'].includes(d.n))
   g+=`<text x="${cx+11}" y="${cy+4}" font-size="11" font-weight="600" fill="var(--ink2)">${esc(d.n)}</text>`;
 });
 svg.innerHTML=g;
}
svg.addEventListener('pointermove',e=>{
 const t=e.target.closest('.dot');
 if(!t){tip.style.opacity=0;return}
 const d=DATA[+t.dataset.i];
 tip.innerHTML=`<b>${esc(d.n)}</b> <span class="r">${d.t} · ${d.p}</span><br>£${d.c.toFixed(1)}m · <b>${d.x}</b> xPts/match<br><span class="r">${d.s}% owned${d.v4?' · in squad v4':''}</span>`;
 tip.style.opacity=1;
 tip.style.left=Math.min(e.clientX+14,innerWidth-250)+'px';
 tip.style.top=(e.clientY+14)+'px';
});
svg.addEventListener('pointerleave',()=>tip.style.opacity=0);
const chips=document.getElementById('chips');
['DEF','MID','FWD','GKP'].forEach(p=>{
 const b=document.createElement('button');
 b.className='chip';b.dataset.p=p;b.setAttribute('aria-pressed','true');
 b.innerHTML=`<span class="sw" style="background:${COL[p]}"></span>${p}`;
 b.onclick=()=>{on[p]=!on[p];b.setAttribute('aria-pressed',on[p]);draw()};
 chips.appendChild(b);
});
const ht=document.getElementById('heatmap');
ht.innerHTML='<tr><th></th>'+[1,2,3,4,5,6].map(g=>`<th class="num" style="text-align:center">GW${g}</th>`).join('')+'</tr>'+
 HEAT.map(r=>'<tr><td class="teamlab">'+r.team+'</td>'+r.gws.map(g=>g?`<td><div class="cell d${g.d}">${g.h?g.o.toUpperCase():g.o.toLowerCase()}</div></td>`:'<td></td>').join('')+'</tr>').join('');
document.querySelector('#squad tbody').innerHTML=SQUAD.map(r=>
 `<tr class="${r.xi?'xi':''}"><td><b>${esc(r.n)}</b></td><td>${r.t}</td><td>${r.p}</td><td class="num">${r.c.toFixed(1)}</td><td class="num"><b>${r.x.toFixed(2)}</b></td><td><span class="pill">${r.xi?'XI':'Bench'}</span></td></tr>`).join('');
draw();
</script>
"""
html = (html.replace('__DATA__', json.dumps(data, ensure_ascii=False))
            .replace('__HEAT__', json.dumps(heat, ensure_ascii=False))
            .replace('__SQUAD__', json.dumps(squad_rows, ensure_ascii=False)))
open('dashboard.html', 'w', encoding='utf-8').write(html)
print(f'dashboard.html written: {len(data)} players, {len(heat)} teams')
