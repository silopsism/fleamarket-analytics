"""Shared visual theme: one source of truth for both page templates.

Direction: matchday programme meets trading desk. Anton (heavy condensed poster
type) for headings and scoreboard numbers, Archivo for everything else, tabular
figures throughout, and a floodlit pitch-ink dark mode. The faces are embedded
from assets/ so a page looks right served from anywhere, or opened from disk.
"""
import base64
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _face(name):
    try:
        with open(os.path.join(_HERE, 'assets', name), 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ''


def fonts():
    anton, archivo = _face('anton.woff2'), _face('archivo.woff2')
    out = ''
    if anton:
        out += ("@font-face{font-family:Anton;src:url(data:font/woff2;base64,%s) "
                "format('woff2');font-weight:400;font-style:normal;font-display:swap}" % anton)
    if archivo:
        out += ("@font-face{font-family:Archivo;src:url(data:font/woff2;base64,%s) "
                "format('woff2');font-weight:400 700;font-style:normal;font-display:swap}" % archivo)
    return out


TOKENS = """
:root{color-scheme:light;
 --bg:#f4f6f4;--surface:#ffffff;--sunk:#eceff0;
 --ink:#0e1411;--ink2:#4a544e;--muted:#7d867f;
 --grid:#dfe4e0;--axis:#b9c1bb;--ring:rgba(14,20,17,.12);
 --accent:#5b2bd9;--accent-soft:#efe9ff;--lime:#a8d600;--lime-ink:#1d2a00;
 --glow:rgba(91,43,217,.10);
 --up:#12833c;--down:#c81e4a;--warn:#b45309;
 --def:#2a78d6;--mid:#eb6834;--fwd:#1baf7a;--gkp:#7d867f;
 --h2:#cde2fb;--h3:#86b6ef;--h4:#3987e5;--h5:#104281;
 --f1:#157f45;--f1i:#fff;--f2:#a7dcb9;--f2i:#08210f;--f3:#e6eae7;--f3i:#39423b;
 --f4:#f4b8c3;--f4i:#2b0a11;--f5:#bf1b3a;--f5i:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --bg:#0b100d;--surface:#141b16;--sunk:#101710;
 --ink:#f1f5f1;--ink2:#b6c1b8;--muted:#7f8a81;
 --grid:#243028;--axis:#334237;--ring:rgba(241,245,241,.12);
 --accent:#a98bff;--accent-soft:#231a3d;--lime:#c8f53c;--lime-ink:#0b100d;
 --glow:rgba(169,139,255,.16);
 --up:#3ecf6a;--down:#ff5c7a;--warn:#fbbf24;
 --def:#3987e5;--mid:#ff7a45;--fwd:#25c78b;--gkp:#7f8a81;
 --f1:#1e7a48;--f1i:#eafff1;--f2:#24503a;--f2i:#cfeadb;--f3:#212a24;--f3i:#b6c1b8;
 --f4:#56212f;--f4i:#ffd7de;--f5:#a3153a;--f5i:#ffe9ee}}
:root[data-theme="dark"]{color-scheme:dark;
 --bg:#0b100d;--surface:#141b16;--sunk:#101710;
 --ink:#f1f5f1;--ink2:#b6c1b8;--muted:#7f8a81;
 --grid:#243028;--axis:#334237;--ring:rgba(241,245,241,.12);
 --accent:#a98bff;--accent-soft:#231a3d;--lime:#c8f53c;--lime-ink:#0b100d;
 --glow:rgba(169,139,255,.16);
 --up:#3ecf6a;--down:#ff5c7a;--warn:#fbbf24;
 --def:#3987e5;--mid:#ff7a45;--fwd:#25c78b;--gkp:#7f8a81;
 --f1:#1e7a48;--f1i:#eafff1;--f2:#24503a;--f2i:#cfeadb;--f3:#212a24;--f3i:#b6c1b8;
 --f4:#56212f;--f4i:#ffd7de;--f5:#a3153a;--f5i:#ffe9ee}
"""

BASE = """
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);
 font:15px/1.5 Archivo,system-ui,-apple-system,"Segoe UI",sans-serif;
 font-variant-numeric:tabular-nums;padding:0 20px 70px;
 background-image:repeating-linear-gradient(115deg,transparent 0 22px,var(--sunk) 22px 23px);
 background-attachment:fixed}
body:before{content:"";position:fixed;inset:-10% 0 auto;height:340px;pointer-events:none;
 z-index:0;background:radial-gradient(60% 100% at 50% 0,var(--glow),transparent 70%)}
.wrap{position:relative;z-index:1}
.wrap{max-width:1000px;margin:0 auto}

/* masthead: pitch stripes behind a poster-weight wordmark */
.brand{display:flex;align-items:center;gap:12px;padding:18px 18px 16px;margin:10px -6px 0;
 position:relative;overflow:hidden;border-radius:14px;background:var(--accent);
 box-shadow:0 6px 22px -12px var(--accent)}
.brand:before{content:"";position:absolute;right:-18px;top:-34px;width:150px;height:150px;
 z-index:0;background:#fff;opacity:.16;
 -webkit-mask:var(--emb-ball) no-repeat center/contain;
 mask:var(--emb-ball) no-repeat center/contain}
.brand:after{content:"";position:absolute;inset:0;z-index:0;
 background:repeating-linear-gradient(90deg,transparent 0 40px,rgba(255,255,255,.06) 40px 80px)}
.brand>*{position:relative;z-index:1}
.brand .mark{font:400 34px/1 Anton,Impact,sans-serif;letter-spacing:.015em;
 text-transform:uppercase;color:#fff}
.brand .mark em{font-style:normal;color:var(--lime)}
.brand .season{font:700 10px/1 Archivo;letter-spacing:.17em;text-transform:uppercase;
 color:#fff;padding:5px 8px;border:1px solid rgba(255,255,255,.45);border-radius:5px}

h1{font:400 clamp(30px,5vw,44px)/1.02 Anton,Impact,sans-serif;letter-spacing:.005em;
 text-transform:uppercase;text-wrap:balance;margin:6px 0 0}
h2{font:400 22px/1.1 Anton,Impact,sans-serif;letter-spacing:.02em;text-transform:uppercase;
 display:flex;align-items:center;gap:11px;margin-bottom:4px}
h2:before{content:"";width:14px;height:14px;background:var(--accent);flex:none;
 border-radius:3px;box-shadow:3px 3px 0 0 var(--lime)}
h3{font:700 12px/1.2 Archivo;letter-spacing:.1em;text-transform:uppercase;
 color:var(--ink2);margin-bottom:9px}
.sub{color:var(--ink2);max-width:64ch;margin-top:8px}
.note{font-size:12.5px;color:var(--muted);margin-bottom:14px}
.mut{font:700 10.5px/1 Archivo;letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
.eyebrow{font:700 11px/1 Archivo;letter-spacing:.16em;text-transform:uppercase;color:var(--accent)}
a{color:var(--accent)}

.card{background:var(--surface);border:1px solid var(--ring);border-radius:14px;
 padding:22px;margin-top:22px;position:relative;overflow:hidden}
.card:before{content:"";position:absolute;left:0;right:0;top:0;height:4px;
 background:linear-gradient(90deg,var(--accent) 0 38%,var(--lime) 38% 52%,transparent 52%)}

/* tabs: sticky, lime marker on the live one */
.tabs{display:flex;overflow-x:auto;border-bottom:2px solid var(--grid);
 margin:0 0 4px;scrollbar-width:none;position:sticky;top:0;background:var(--bg);z-index:6}
.tabs::-webkit-scrollbar{display:none}
.tab{padding:11px 15px;font:700 12px/1 Archivo;letter-spacing:.11em;text-transform:uppercase;
 color:var(--muted);text-decoration:none;white-space:nowrap;margin-bottom:-2px;
 border-bottom:3px solid transparent;border-radius:7px 7px 0 0;transition:all .12s}
.tab:hover{color:var(--ink);background:var(--sunk)}
.tab[aria-current]{color:#fff;background:var(--accent);border-bottom-color:var(--lime)}
.tabpane{display:none}
.tabpane.active{display:block}

/* scoreboard tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin-top:16px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:12px;
 padding:14px 15px 15px 20px;position:relative;overflow:hidden;--tint:var(--accent)}
.tile:after{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:var(--tint)}
.tile:before{content:"";position:absolute;right:-30px;bottom:-46px;width:112px;height:112px;
 border-radius:50%;background:var(--tint);opacity:.09}
.tile:nth-child(2){--tint:var(--def)}
.tile:nth-child(3){--tint:var(--mid)}
.tile:nth-child(4){--tint:var(--fwd)}
.tile:nth-child(5){--tint:var(--warn)}
.tile:nth-child(6){--tint:var(--accent)}
.tile .tl{font:700 10px/1 Archivo;letter-spacing:.13em;text-transform:uppercase;color:var(--muted)}
.tile .tv{font:400 31px/1.05 Anton,Impact,sans-serif;letter-spacing:.01em;margin-top:8px;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .ts{font-size:12px;color:var(--ink2);margin-top:3px}

/* chips */
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px}
.chip{border:1px solid var(--grid);background:var(--surface);color:var(--ink2);
 font:700 11.5px/1 Archivo;letter-spacing:.05em;padding:7px 12px;border-radius:99px;
 cursor:pointer;display:flex;align-items:center;gap:7px;transition:all .12s}
.chip:hover{border-color:var(--axis);color:var(--ink)}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.chip .sw{width:9px;height:9px;border-radius:2px}
.chip[data-p="GKP"] .sw{border-radius:1px}

/* tables */
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{font:700 10.5px/1.3 Archivo;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
 text-align:left;padding:8px 10px;border-bottom:2px solid var(--grid);white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid var(--grid);font-size:13.5px;white-space:nowrap}
tbody tr:hover td{background:var(--sunk)}
td.num,th.num{text-align:right}
tfoot th{border-top:2px solid var(--axis);border-bottom:0;color:var(--ink);font-size:11px}
.pill{display:inline-block;font:700 9.5px/1.6 Archivo;letter-spacing:.08em;text-transform:uppercase;
 border:1px solid var(--grid);border-radius:99px;padding:1px 8px;color:var(--muted)}
.xi .pill{color:var(--accent);border-color:var(--accent)}
tr.benchstart td{border-top:2px solid var(--axis)}
.low{color:var(--down);font-weight:700}
.selcol{background:var(--accent-soft)}
.absent{opacity:.34}
th.gwsel{cursor:pointer;color:var(--ink2)}
th.gwsel:hover{color:var(--accent)}

/* fixture heat cells */
.hm td{padding:3px}
.cell{min-width:54px;text-align:center;border-radius:5px;
 font:700 11px/1.5 Archivo;letter-spacing:.03em;padding:5px 4px}
.d2{background:var(--h2);color:#08121f}.d3{background:var(--h3);color:#08121f}
.d4{background:var(--h4);color:#fff}.d5{background:var(--h5);color:#fff}
/* two-directional fixture cells: f1 kindest .. f5 harshest, applied to the
   attacking read and the defensive read independently */
.f1{background:var(--f1);color:var(--f1i)}.f2{background:var(--f2);color:var(--f2i)}
.f3{background:var(--f3);color:var(--f3i)}.f4{background:var(--f4);color:var(--f4i)}
.f5{background:var(--f5);color:var(--f5i)}
.cell{position:relative}
.cell.f0{background:var(--sunk);color:var(--ink2)}
.cell .cn{display:block;font:700 10px/1.35 Archivo;opacity:.78;letter-spacing:0}
.cell .bars{display:flex;gap:2px;margin-top:4px}
.cell .bars i{flex:1;height:6px;border-radius:2px}
.cell.odds:before{content:"";position:absolute;top:3px;right:3px;width:4px;height:4px;
 border-radius:50%;background:currentColor;opacity:.5}
.hmkey{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:12px 0 2px;
 font:700 10.5px/1 Archivo;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.hmkey .sc{display:flex;gap:3px}
.hmkey .sc i{width:17px;height:9px;border-radius:2px}
.teamlab{font:700 12px/1 Archivo;letter-spacing:.06em;padding-right:10px;text-transform:uppercase}
/* a player whose expected minutes climb across the horizon, rather than a
   player whose first week is simply low */
.ramp{font:700 9.5px/1 Archivo;letter-spacing:.07em;text-transform:uppercase;
 color:var(--warn);border:1px solid var(--warn);border-radius:4px;padding:2px 4px;
 white-space:nowrap;vertical-align:1px}

/* squad on a pitch: mown stripes, markings, one card per player */
.pitch{position:relative;border-radius:14px;overflow:hidden;padding:16px 8px 12px;
 background:
  repeating-linear-gradient(0deg,#1f7a3f 0 34px,#1c6f39 34px 68px);
 box-shadow:inset 0 0 60px rgba(0,0,0,.28)}
.pitch:before{content:"";position:absolute;inset:8px;border:2px solid rgba(255,255,255,.28);
 border-radius:6px;pointer-events:none}
.pitch:after{content:"";position:absolute;left:50%;top:8px;width:104px;height:104px;
 transform:translate(-50%,-52px);border:2px solid rgba(255,255,255,.28);border-radius:50%;
 pointer-events:none}
.pitch .goalbox{position:absolute;left:50%;transform:translateX(-50%);
 border:2px solid rgba(255,255,255,.26);border-top:0;pointer-events:none}
.pitch .goalbox.b18{top:8px;width:min(58%,340px);height:74px;border-radius:0 0 4px 4px}
.pitch .goalbox.b6{top:8px;width:min(28%,168px);height:34px;border-radius:0 0 4px 4px}
.pline{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;
 position:relative;z-index:1;margin:10px 0}

.pcard{width:92px;background:rgba(10,20,14,.62);border:1px solid rgba(255,255,255,.16);
 border-radius:10px;padding:6px 5px 5px;text-align:center;color:#fff;
 backdrop-filter:blur(2px);position:relative}
.pcard .shirt{display:block;margin:0 auto 3px}
/* two lines rather than an ellipsis: "Calvert-Lewin" and "B.Fernandes" both
   clip at card width, and a fixed two-line box keeps every card the same height */
.pcard .pn{font:700 11.5px/1.2 Archivo;letter-spacing:.01em;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
 overflow:hidden;overflow-wrap:anywhere;min-height:2.4em}
.pcard .pc{font:700 9px/1.3 Archivo;letter-spacing:.11em;text-transform:uppercase;
 color:rgba(255,255,255,.68)}
.pcard .px{display:flex;gap:3px;justify-content:center;margin-top:4px}
.pcard .px b{flex:1;font:700 11px/1.5 Archivo;background:rgba(255,255,255,.16);
 border-radius:4px}
.pcard .px b:first-child{background:var(--lime);color:var(--lime-ink)}
.pcard .badge{position:absolute;top:-6px;right:-6px;width:19px;height:19px;border-radius:50%;
 font:700 10px/19px Archivo;background:var(--lime);color:var(--lime-ink);
 box-shadow:0 1px 4px rgba(0,0,0,.4)}
.pcard .badge.v{background:#fff;color:#111}
.pcard.movein{border-color:var(--lime);box-shadow:0 0 0 1px var(--lime)}
.pcard.movein:after{content:"IN";position:absolute;left:-6px;top:-6px;padding:0 4px;
 border-radius:4px;font:700 9px/16px Archivo;letter-spacing:.06em;
 background:var(--lime);color:var(--lime-ink)}

.benchstrip{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;
 margin-top:10px;padding:12px 8px;border-radius:12px;background:var(--sunk);
 border:1px solid var(--ring)}
.benchstrip .pcard{background:var(--surface);border-color:var(--ring);color:var(--ink)}
.benchstrip .pcard .pc{color:var(--muted)}
.benchstrip .pcard .px b{background:var(--bg);color:var(--ink)}
.benchstrip .pcard .px b:first-child{background:var(--accent-soft);color:var(--accent)}
.pitchhead{display:flex;justify-content:space-between;align-items:baseline;
 gap:12px;flex-wrap:wrap;margin-bottom:6px}
@media (max-width:560px){
 .pcard{width:74px}
 .pcard .pn{font-size:10.5px;min-height:2.4em}
 .pline{gap:5px;margin:7px 0}
 .pitch{padding:12px 4px 8px}
}

/* movement + mini lists */
.up,.mvup{color:var(--up);font-weight:700}
.down,.mvdn{color:var(--down);font-weight:700}
.mini{font-size:13.5px;line-height:1.45}
.mini .row{display:flex;justify-content:space-between;gap:10px;padding:6px 0;
 border-bottom:1px solid var(--grid)}
.mini .row:last-child{border-bottom:0}

/* charts */
#scat,#diff,#frontier{width:100%;height:auto;display:block}
.tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--axis);
 border-radius:9px;padding:9px 12px;font-size:12.5px;box-shadow:0 6px 20px rgba(0,0,0,.22);
 opacity:0;transition:opacity .12s;z-index:9;max-width:240px}
.tip b{font-size:13.5px}
.tip .r{color:var(--ink2)}

/* layout helpers */
.cols{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:16px;align-items:start}
.cols3{display:grid;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));gap:24px;
 margin-top:14px;align-items:start}
.stack{display:flex;flex-direction:column;gap:26px}
@media(max-width:700px){.cols{grid-template-columns:1fr}}

/* section emblem, watermarked into the top-right of each card */
.card:after{content:"";position:absolute;right:-14px;top:-14px;width:132px;height:132px;
 background:var(--ink);opacity:.07;pointer-events:none;z-index:0;
 -webkit-mask:var(--emb) no-repeat center/contain;mask:var(--emb) no-repeat center/contain}
.card>*{position:relative;z-index:1}
.tabpane,.wmzone{position:relative}

button,input,textarea,select{font-family:Archivo,system-ui,sans-serif}
footer{margin-top:28px;padding-top:14px;border-top:1px solid var(--grid);
 font-size:12px;color:var(--muted);max-width:74ch}
"""


def _emb(body, sw='1.3'):
    """A line-art SVG as a CSS mask URL. Masks take the theme's ink colour, so
    emblems follow light/dark automatically."""
    import urllib.parse
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
           "stroke='black' stroke-width='%s' stroke-linecap='round' "
           "stroke-linejoin='round'>%s</svg>" % (sw, body))
    return 'url("data:image/svg+xml,' + urllib.parse.quote(svg) + '")'


EMBLEMS = {
    'overview': _emb("<circle cx='12' cy='12' r='9'/>"
                     "<path d='M12 6.4l3.4 2.5-1.3 4h-4.2l-1.3-4z'/>"
                     "<path d='M12 3v3.4M4.4 9.3l2.9 1.1M19.6 9.3l-2.9 1.1"
                     "M7.2 19.7l1.7-3.2M16.8 19.7l-1.7-3.2'/>"),
    'value': _emb("<path d='M3 20.5h18'/><path d='M5 20.5V13M10.3 20.5V8.5"
                  "M15.6 20.5V15.5M20.4 20.5V4.5'/>", sw='1.9'),
    'planner': _emb("<rect x='3' y='5' width='18' height='16' rx='2'/>"
                    "<path d='M3 10.2h18M8 3v4M16 3v4'/>"
                    "<path d='M7.5 14h3M13.5 14h3M7.5 17.6h3M13.5 17.6h3'/>"),
    'market': _emb("<path d='M3.5 18.5l5.2-6 3.8 2.8 7-8.3'/>"
                   "<path d='M14.4 7h5.1v5'/><path d='M3.5 21h17'/>", sw='1.7'),
    'fixtures': _emb("<rect x='2.5' y='4.5' width='19' height='15' rx='1.5'/>"
                     "<path d='M12 4.5v15'/><circle cx='12' cy='12' r='2.8'/>"
                     "<path d='M2.5 9h3.2v6H2.5M21.5 9h-3.2v6h3.2'/>"),
    'news': _emb("<path d='M3.8 10.2v3.6l10 4V6.2l-10 4z'/>"
                 "<path d='M13.8 8.6c2.6.8 4.2 2 4.2 3.4s-1.6 2.6-4.2 3.4'/>"
                 "<path d='M6.2 14.6V19h3v-3.5'/>"),
    'squads': _emb("<path d='M9 3.4 4.4 6l1.6 4.2 2-.8V20.6h8V9.4l2 .8L19.6 6 15 3.4"
                   "c-.9 1.3-1.8 1.9-3 1.9s-2.1-.6-3-1.9z'/>"),
}


def emblem_css():
    out = [':root{--emb:%s;--emb-ball:%s}'
           % (EMBLEMS['overview'], EMBLEMS['overview'])]
    for key, url in EMBLEMS.items():
        out.append('.tabpane[data-tab="%s"],.sec-%s{--emb:%s}' % (key, key, url))
    return ''.join(out)


def style_block():
    """The full <style> element shared by every page."""
    return '<style>' + fonts() + TOKENS + BASE + emblem_css() + '</style>'
