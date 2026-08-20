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
 --h2:#cde2fb;--h3:#86b6ef;--h4:#3987e5;--h5:#104281}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --bg:#0b100d;--surface:#141b16;--sunk:#101710;
 --ink:#f1f5f1;--ink2:#b6c1b8;--muted:#7f8a81;
 --grid:#243028;--axis:#334237;--ring:rgba(241,245,241,.12);
 --accent:#a98bff;--accent-soft:#231a3d;--lime:#c8f53c;--lime-ink:#0b100d;
 --glow:rgba(169,139,255,.16);
 --up:#3ecf6a;--down:#ff5c7a;--warn:#fbbf24;
 --def:#3987e5;--mid:#ff7a45;--fwd:#25c78b;--gkp:#7f8a81}}
:root[data-theme="dark"]{color-scheme:dark;
 --bg:#0b100d;--surface:#141b16;--sunk:#101710;
 --ink:#f1f5f1;--ink2:#b6c1b8;--muted:#7f8a81;
 --grid:#243028;--axis:#334237;--ring:rgba(241,245,241,.12);
 --accent:#a98bff;--accent-soft:#231a3d;--lime:#c8f53c;--lime-ink:#0b100d;
 --glow:rgba(169,139,255,.16);
 --up:#3ecf6a;--down:#ff5c7a;--warn:#fbbf24;
 --def:#3987e5;--mid:#ff7a45;--fwd:#25c78b;--gkp:#7f8a81}
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
.brand:before{content:"FPL";position:absolute;right:14px;top:-26px;z-index:0;
 font:400 108px/1 Anton,Impact,sans-serif;color:#fff;opacity:.13;letter-spacing:-.02em}
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
.teamlab{font:700 12px/1 Archivo;letter-spacing:.06em;padding-right:10px;text-transform:uppercase}

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

/* giant ghost type behind a section, set per pane via --wm */
.tabpane,.wmzone{position:relative}
.tabpane:before,.wmzone:before{content:var(--wm,"");position:absolute;right:0;top:-6px;
 font:400 clamp(64px,12vw,132px)/.8 Anton,Impact,sans-serif;letter-spacing:-.02em;
 color:var(--ink);opacity:.075;pointer-events:none;z-index:0;white-space:nowrap;
 text-transform:uppercase}
.tabpane[data-tab="overview"]{--wm:"Overview"}
.tabpane[data-tab="value"]{--wm:"Value"}
.tabpane[data-tab="planner"]{--wm:"Planner"}
.tabpane[data-tab="market"]{--wm:"Market"}
.tabpane[data-tab="fixtures"]{--wm:"Fixtures"}

button,input,textarea,select{font-family:Archivo,system-ui,sans-serif}
footer{margin-top:28px;padding-top:14px;border-top:1px solid var(--grid);
 font-size:12px;color:var(--muted);max-width:74ch}
"""


def style_block():
    """The full <style> element shared by every page."""
    return '<style>' + fonts() + TOKENS + BASE + '</style>'
