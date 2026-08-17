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


pts = [p for p in players if p['xpts'] >= 1.8 or pkey(p) in V4]
data = [{'n': p['name'], 't': teams[p['team']], 'p': pos_name[p['pos']],
         'c': p['price'], 'x': round(p['xpts'], 2), 'xn': round(p['xnext'], 2),
         's': p['sel'], 'v4': pkey(p) in V4, 'xi': pkey(p) in set(V4_XI)} for p in pts]

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
                       'c': p['price'], 'x': round(p['xpts'], 2),
                       'xn': round(p['xnext'], 2),
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
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:16px}
@media(max-width:700px){.cols{grid-template-columns:1fr}}
h3{font-size:13.5px;margin-bottom:8px}
.mut{font-size:11px;color:var(--muted);font-weight:400;letter-spacing:.04em;text-transform:uppercase}
#diff{width:100%;height:auto;display:block}
</style>
<div class="wrap">
<header>
 <div class="eyebrow">Fleamarket Bargains · 2026/27 · Phase 1 model</div>
 <h1>Fleamarket Analytics</h1>
 <p class="sub">Every player scored from last season's Opta rates (xG, xA, clean sheets,
 defensive contributions), adjusted for opening fixtures. __SUBNOTE__Deadline: Fri 21 Aug, 18:30 UK.</p>
</header>

<section class="card">
 <h2>Value map — price vs expected points</h2>
 <p class="note">xPts = expected points per match averaged over the next 4 gameweeks' fixtures, from prior-season rates. Tooltips also show the single-fixture GW1 projection. __RINGNOTE__Hover or tap any dot. Goalkeepers drawn as gray squares.</p>
 <div class="chips" id="chips"></div>
 <svg id="scat" viewBox="0 0 940 520" role="img" aria-label="Scatter plot of player price against expected points per match"></svg>
</section>

<section class="card">
 <h2>Differentials &amp; traps — the model vs the crowd</h2>
 <p class="note">Ownership against model score. Top-left: gems the crowd hasn't found. Bottom-right: popular picks the model doubts. Ownership axis is stretched at the low end.</p>
 <svg id="diff" viewBox="0 0 940 440" role="img" aria-label="Scatter of ownership against expected points per match"></svg>
 <div class="cols">
  <div><h3>Top differentials <span class="mut">under 10% owned</span></h3>
  <div class="scroll"><table><tr><th>Player</th><th>Team</th><th class="num">£m</th><th class="num">Own%</th><th class="num">xPts</th></tr>__DIFFROWS__</table></div></div>
  <div><h3>Crowd traps <span class="mut">15%+ owned, model skeptical</span></h3>
  <div class="scroll"><table><tr><th>Player</th><th>Team</th><th class="num">£m</th><th class="num">Own%</th><th class="num">xPts</th></tr>__TRAPROWS__</table></div>
  <p class="note" style="margin:8px 0 0">Model uses last season's rates — players in new, bigger roles this season may be unfairly flagged.</p></div>
 </div>
</section>

__VALUEBANDS__

<section class="card">
 <h2>Opening fixtures — GW1–6</h2>
 <p class="note">Sorted easiest run first. Darker = harder (FPL difficulty rating). Uppercase = home.</p>
 <div class="scroll hm"><table id="heatmap"></table></div>
</section>

__SQUADSEC__
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
function bindTips(el){
 el.addEventListener('pointermove',e=>{
  const t=e.target.closest('.dot');
  if(!t){tip.style.opacity=0;return}
  const d=DATA[+t.dataset.i];
  tip.innerHTML=`<b>${esc(d.n)}</b> <span class="r">${d.t} · ${d.p}</span><br>£${d.c.toFixed(1)}m · <b>${d.x}</b> xPts (next 4 GWs) · GW1: <b>${d.xn}</b><br><span class="r">${d.s}% owned${d.v4?' · in squad v5':''}</span>`;
  tip.style.opacity=1;
  tip.style.left=Math.min(e.clientX+14,innerWidth-250)+'px';
  tip.style.top=(e.clientY+14)+'px';
 });
 el.addEventListener('pointerleave',()=>tip.style.opacity=0);
}
bindTips(svg);

// differentials quadrant: x = ownership (sqrt-stretched), y = xPts
const dsvg=document.getElementById('diff');
(function(){
 const W=940,H=440,L=52,R=16,T=20,B=44,SMAX=80;
 const SX=v=>L+Math.sqrt(v/SMAX)*(W-L-R), SY=v=>H-B-(v-0)/(ymax-0)*(H-T-B);
 let g='';
 [1,5,15,40,75].forEach(v=>{g+=`<line x1="${SX(v)}" x2="${SX(v)}" y1="${T}" y2="${H-B}" stroke="var(--grid)"/>`+
  `<text x="${SX(v)}" y="${H-B+18}" text-anchor="middle" font-size="11" fill="var(--muted)">${v}%</text>`});
 for(let p=1;p<=ymax;p++) g+=`<text x="${L-8}" y="${SY(p)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${p}</text>`;
 g+=`<line x1="${L}" x2="${W-R}" y1="${SY(0)}" y2="${SY(0)}" stroke="var(--axis)"/>`;
 g+=`<line x1="${SX(15)}" x2="${SX(15)}" y1="${T}" y2="${H-B}" stroke="var(--axis)" stroke-dasharray="4 4"/>`;
 g+=`<line x1="${L}" x2="${W-R}" y1="${SY(3.2)}" y2="${SY(3.2)}" stroke="var(--axis)" stroke-dasharray="4 4"/>`;
 g+=`<text x="${L+8}" y="${T+14}" font-size="11" fill="var(--muted)" font-weight="700" letter-spacing=".08em">DIFFERENTIALS</text>`;
 g+=`<text x="${W-R-8}" y="${T+14}" text-anchor="end" font-size="11" fill="var(--muted)" font-weight="700" letter-spacing=".08em">ESSENTIALS</text>`;
 g+=`<text x="${W-R-8}" y="${H-B-10}" text-anchor="end" font-size="11" fill="var(--muted)" font-weight="700" letter-spacing=".08em">TRAPS</text>`;
 g+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" font-size="11.5" fill="var(--ink2)">Ownership (%)</text>`;
 DATA.forEach((d,i)=>{
  const cx=SX(Math.min(d.s,SMAX)),cy=SY(d.x),c=COL[d.p];
  const mark=d.p==='GKP'?`<rect x="${cx-4}" y="${cy-4}" width="8" height="8" fill="${c}"/>`:`<circle cx="${cx}" cy="${cy}" r="4.5" fill="${c}"/>`;
  g+=`<g class="dot" data-i="${i}">${d.v4?`<circle cx="${cx}" cy="${cy}" r="8.5" fill="none" stroke="var(--ink)" stroke-width="1.6"/>`:''}${mark}<circle cx="${cx}" cy="${cy}" r="12" fill="transparent"/></g>`;
 });
 dsvg.innerHTML=g;
})();
bindTips(dsvg);
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
const sqEl=document.querySelector('#squad tbody');
if(sqEl)sqEl.innerHTML=SQUAD.map(r=>
 `<tr class="${r.xi?'xi':''}"><td><b>${esc(r.n)}</b></td><td>${r.t}</td><td>${r.p}</td><td class="num">${r.c.toFixed(1)}</td><td class="num"><b>${r.x.toFixed(2)}</b></td><td class="num">${r.xn.toFixed(2)}</td><td><span class="pill">${r.xi?'XI':'Bench'}</span></td></tr>`).join('');
draw();
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
    1: [(4.0, 4.0, 2), (4.5, 4.5, 2), (5.0, 5.0, 2), (5.5, 6.5, 2)],
    2: [(4.0, 4.0, 2), (4.5, 4.5, 2), (5.0, 5.0, 2), (5.5, 5.5, 2),
        (6.0, 6.0, 2), (6.5, 8.5, 3)],
    3: [(4.5, 4.5, 2), (5.0, 5.0, 2), (5.5, 5.5, 2), (6.0, 6.0, 2),
        (6.5, 6.5, 2), (7.0, 7.0, 2), (7.5, 7.5, 2), (8.0, 8.0, 2),
        (8.5, 9.5, 2), (10.0, 16.0, 2)],
    4: [(4.5, 4.5, 2), (5.0, 5.0, 2), (5.5, 5.5, 2), (6.0, 6.0, 2),
        (6.5, 6.5, 2), (7.0, 7.0, 2), (7.5, 7.5, 2), (8.0, 8.0, 2),
        (8.5, 16.0, 3)],
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
            '<p class="note">Top model scores per price band — only players expected to start '
            '(45+ expected minutes). The cheapest name that matches an expensive one is the value pick.</p>'
            f"<div class='cols'>{cols[0]}{cols[1]}</div><div class='cols' style='margin-top:20px'>{cols[2]}{cols[3]}</div>"
            + note + 'Scores are per team gameweek and price in availability.</p></section>')


SQUAD_SEC = """<section class="card">
 <h2>Squad v5 — £100.0m</h2>
 <p class="note">Starting XI then bench. xPts = per-match average over the next 4 GWs; GW1 = next fixture only.</p>
 <div class="scroll"><table id="squad"><thead><tr>
 <th>Player</th><th>Team</th><th>Pos</th><th class="num">£m</th><th class="num">xPts (next 4)</th><th class="num">GW1</th><th>Role</th>
 </tr></thead><tbody></tbody></table></div>
</section>"""


def emit(path, personal):
    # public copy strips squad markers entirely (no rings, labels, table, or
    # flags in the embedded JSON) so nothing about our team leaks pre-deadline
    dat = data if personal else [{**r, 'v4': False, 'xi': False} for r in data]
    page = (html.replace('__VALUEBANDS__', band_tables(personal))
                .replace('__SQUADSEC__', SQUAD_SEC if personal else '')
                .replace('__SUBNOTE__', 'Squad v4 marked with rings. ' if personal else '')
                .replace('__RINGNOTE__', 'Ringed dots = our squad. ' if personal else '')
                .replace('__DIFFROWS__', table_rows(diffs))
                .replace('__TRAPROWS__', table_rows(trapped))
                .replace('__DATA__', json.dumps(dat, ensure_ascii=False))
                .replace('__HEAT__', json.dumps(heat, ensure_ascii=False))
                .replace('__SQUAD__', json.dumps(squad_rows if personal else [], ensure_ascii=False)))
    open(path, 'w', encoding='utf-8').write(page)


emit('dashboard.html', False)      # public: general analysis only (served by app.py)
emit('my_dashboard.html', True)    # personal: includes squad v4 (artifact / local viewing)
print(f'dashboard.html (public) + my_dashboard.html (personal): {len(data)} players, {len(heat)} teams')
