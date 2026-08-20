"""Telegram push notifications: biggest ownership movers and major news.

Credentials come from the environment (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) or
a gitignored .telegram.env next to this file. With neither, every function is a
no-op, so the app runs fine without notifications configured.

Only genuinely new items are sent — state lives in the snapshot volume, so a
redeploy doesn't cause a flood of repeats. Quiet hours avoid 3am pings; anything
found overnight is included in the first morning digest instead.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

STATE = os.path.join(os.environ.get('FPL_DATA_DIR', 'data'), 'notified.json')
QUIET_FROM, QUIET_TO = 23, 6          # UK local hours, inclusive-exclusive
MOVE_THRESHOLD = 0.2                  # percentage points of ownership
# pre-deadline, ownership drift IS the transfer market: transfers_in_event
# only counts once a gameweek is live, so d_sel carries the whole signal
MAX_ITEMS = 6


def creds():
    tok = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not tok or not chat:
        try:
            for line in open('.telegram.env', encoding='utf-8'):
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    if k.strip() == 'TELEGRAM_BOT_TOKEN' and not tok:
                        tok = v.strip()
                    elif k.strip() == 'TELEGRAM_CHAT_ID' and not chat:
                        chat = v.strip()
        except FileNotFoundError:
            pass
    return tok, chat


def send(text, disable_preview=True):
    """Post one message. Returns True on success, False if unconfigured/failed."""
    tok, chat = creds()
    if not tok or not chat:
        return False
    data = urllib.parse.urlencode({
        'chat_id': chat, 'text': text, 'parse_mode': 'HTML',
        'disable_web_page_preview': 'true' if disable_preview else 'false',
    }).encode()
    try:
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{tok}/sendMessage', data=data)
        r = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return bool(r.get('ok'))
    except Exception:
        return False


def _state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:
        return {'sent': []}


def _save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE) or '.', exist_ok=True)
        st['sent'] = st['sent'][-400:]          # keep the file small
        json.dump(st, open(STATE, 'w', encoding='utf-8'))
    except Exception:
        pass


def _uk_now():
    # UK summer time; good enough for quiet hours
    return datetime.now(timezone.utc) + timedelta(hours=1)


def build_digest(risers, fallers, news, seen):
    """Compose a digest of items not already sent. Returns (text, keys)."""
    lines, keys = [], []

    def esc(s):
        return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    moves = []
    for r in risers:
        if abs(r['d_sel']) < MOVE_THRESHOLD and not r['d_net']:
            continue
        k = f"mv:{r['player']}:{round(r['sel'], 1)}"
        if k in seen:
            continue
        moves.append(f"▲ <b>{esc(r['player'].split('|')[0])}</b> "
                     f"{esc(r['player'].split('|')[1])} {r['d_sel']:+.2f}pp → {r['sel']:.1f}%")
        keys.append(k)
    for r in fallers:
        if abs(r['d_sel']) < MOVE_THRESHOLD and not r['d_net']:
            continue
        k = f"mv:{r['player']}:{round(r['sel'], 1)}"
        if k in seen:
            continue
        moves.append(f"▼ <b>{esc(r['player'].split('|')[0])}</b> "
                     f"{esc(r['player'].split('|')[1])} {r['d_sel']:+.2f}pp → {r['sel']:.1f}%")
        keys.append(k)

    stories = []
    for s in news:
        k = 'nw:' + str(abs(hash(s['player'] + s['headline'][:60])))
        if k in seen:
            continue
        icon = {'reduce': '⚠️', 'raise': '🔼', 'watch': '👀'}.get(s.get('kind'), '📰')
        stories.append(f"{icon} <b>{esc(s['player'].split('|')[0])}</b> "
                       f"{esc(s['player'].split('|')[1])} — {esc(s['headline'][:110])}"
                       f"\n<i>{esc(s.get('source', ''))}</i>")
        keys.append(k)

    if not moves and not stories:
        return None, []
    lines.append(f"<b>Fleamarket</b> · {_uk_now().strftime('%a %H:%M')}")
    if moves:
        lines.append('\n<b>Ownership movers</b>\n' + '\n'.join(moves[:MAX_ITEMS]))
    if stories:
        lines.append('\n<b>News</b>\n' + '\n\n'.join(stories[:4]))
    lines.append('\nhttp://fpl.salwood.co.za')
    return '\n'.join(lines), keys


def maybe_notify(elements, teams, news_payload, hours=6, force=False):
    """Send a digest if there is anything new and we're outside quiet hours."""
    tok, chat = creds()
    if not tok or not chat:
        return 'unconfigured'
    hour = _uk_now().hour
    if not force and (hour >= QUIET_FROM or hour < QUIET_TO):
        return 'quiet hours'
    try:
        import momentum
        risers, fallers, _meta = momentum.recent_moves(elements, teams, hours=hours, top=4)
    except Exception:
        risers, fallers = [], []
    news = []
    if news_payload:
        news = [p for p in (news_payload.get('proposals') or [])
                if p.get('kind') in ('reduce', 'raise', 'watch')]
        news += [{'player': d['player'], 'headline': d['items'][0]['title'],
                  'source': d['items'][0]['source'], 'kind': 'watch'}
                 for d in (news_payload.get('discoveries') or [])[:3]
                 if d.get('items') and d.get('score', 0) >= 8]
    st = _state()
    seen = set(st.get('sent', []))
    text, keys = build_digest(risers, fallers, news, seen)
    if not text:
        return 'nothing new'
    if send(text):
        st['sent'] = list(st.get('sent', [])) + keys
        st['last'] = _uk_now().isoformat(timespec='minutes')
        _save_state(st)
        return f'sent {len(keys)} item(s)'
    return 'send failed'


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        ok = send('<b>Fleamarket</b> · test message ✅\nNotifications are wired up.')
        print('test send:', 'ok' if ok else 'failed (check token/chat id)')
    else:
        boot = json.load(open('bootstrap.json', encoding='utf-8'))
        els = {e['id']: e for e in boot['elements']}
        teams = {t['id']: t['short_name'] for t in boot['teams']}
        try:
            news = json.load(open('news_cache.json', encoding='utf-8'))
        except Exception:
            news = None
        print(maybe_notify(els, teams, news, force=True))
