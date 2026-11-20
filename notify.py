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
# Net transfers only mean something at scale. Once a gameweek is live, 599 of
# 600 players have a non-zero transfers_in_event, so treating "non-zero" as
# newsworthy pushed every player to the phone - one qualified on a net of 105
# transfers out of nine million managers. This is a share of the playerbase.
NET_SHARE = 0.0025                    # 0.25% of managers, ~23k at 9.3m
NET_FLOOR = 15000                     # ...but never less than this

# One scheduled post a week, in the first hour it falls inside a day of the
# deadline. Three or four a day was noise; the decision only gets made once.
DIGEST_LEAD_HOURS = 24

# The exception. An injury to someone you own is worth a same-day push, and
# waiting for FPL to raise a flag can take days - the press knows first. These
# are the sweep's tags for "will not play" and "might not play".
URGENT_TAGS = {'out', 'doubt', 'rotation'}


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
        st['sent'] = list(st.get('sent') or [])[-400:]   # keep the file small
        # levels are per player, so they cannot grow without bound
        json.dump(st, open(STATE, 'w', encoding='utf-8'))
    except Exception:
        pass


def _uk_now():
    # UK summer time; good enough for quiet hours
    return datetime.now(timezone.utc) + timedelta(hours=1)


def net_bar(total_players):
    """How many net transfers count as a real market move."""
    return max(int((total_players or 0) * NET_SHARE), NET_FLOOR)


def _esc(t):
    return (str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def urgent_squad_alerts(cache, owned, seen):
    """Same-day warnings about players the reader actually owns.

    Driven by the news sweep, not by FPL's status field: a club confirms a
    muscle injury on Tuesday and the flag often does not appear until the press
    conference on Friday. The sweep sees the Tuesday story.

    Only players in the squad, only tags that bear on whether he plays, and one
    alert per headline ever.
    """
    out, keys = [], []
    for key, items in (cache.get('players') or {}).items():
        if key not in owned:
            continue
        who, club = key.split('|')
        for it in items:
            tags = set(it.get('tags') or ()) & URGENT_TAGS
            if not tags:
                continue
            k = 'urg:' + str(abs(hash(key + it.get('title', '')[:70])))
            if k in seen:
                continue
            icon = '🚑' if 'out' in tags else ('⚠️' if 'doubt' in tags else '🔄')
            out.append(icon + ' <b>' + _esc(who) + '</b> ' + _esc(club) + ' — '
                       + _esc(it.get('title', '')[:130]) + '\n'
                       + '<i>' + _esc(it.get('source', '')) + ' · '
                       + _esc(it.get('when', '')) + '</i>')
            keys.append(k)
    return out, keys


def deadline_window(events):
    """(event, hours_to_deadline) for the next deadline, or (None, None)."""
    now = datetime.now(timezone.utc)
    for ev in events or []:
        try:
            dl = datetime.strptime(ev['deadline_time'], '%Y-%m-%dT%H:%M:%SZ').replace(
                tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        if dl > now:
            return ev, (dl - now).total_seconds() / 3600
    return None, None


def weekly_digest(elements, teams, event, hours_left, owned, total_players):
    """The one scheduled post: what moved this gameweek, before the deadline.

    Built from the gameweek's own transfer counters rather than snapshot deltas.
    transfers_in_event resets at each deadline, so it IS the week's movement -
    no history to keep, and nothing lost when a container restarts.
    """
    import re as _re
    bar = net_bar(total_players)
    rows = sorted(((e['transfers_in_event'] - e['transfers_out_event'], e)
                   for e in elements.values()), key=lambda r: -r[0])

    def k(n):
        return ('%+.0fk' % (n / 1000)) if abs(n) < 1e6 else ('%+.1fm' % (n / 1e6))

    def line(n, e, arrow, reason=False):
        why = ''
        if reason and e.get('news'):
            why = ' · ' + _esc(_re.sub(r' - .*', '', e['news'])[:40])
        return (arrow + ' <b>' + _esc(e['web_name']) + '</b> '
                + _esc(teams[e['team']]) + ' ' + k(n) + ' → '
                + str(e['selected_by_percent']) + '%' + why)

    dl = datetime.strptime(event['deadline_time'], '%Y-%m-%dT%H:%M:%SZ')
    L = ['<b>Fleamarket · GW%d</b>' % event['id'],
         'Deadline %s UK · %.0fh to go' % (dl.strftime('%a %d %b, %H:%M'), hours_left)]

    if owned:
        mine = [e for e in elements.values()
                if (e['web_name'] + '|' + teams[e['team']]) in owned and e['status'] != 'a']
        L.append('\n<b>Your squad</b>')
        L.append('\n'.join(
            '⚠️ <b>' + _esc(e['web_name']) + '</b> ' + _esc(teams[e['team']])
            + ' — ' + _esc((e['news'] or 'flagged')[:60]) for e in mine)
            if mine else 'Nothing flagged.')

    ins = [(n, e) for n, e in rows if n >= bar][:5]
    outs = [(n, e) for n, e in rows[::-1] if n <= -bar][:5]
    if ins:
        L.append('\n<b>Moving in</b>')
        L.append('\n'.join(line(n, e, '▲') for n, e in ins))
    if outs:
        L.append('\n<b>Moving out</b>')
        L.append('\n'.join(line(n, e, '▼', reason=True) for n, e in outs))

    rise = [e for e in elements.values()
            if e['cost_change_event'] > 0 and float(e['selected_by_percent']) >= 5]
    fall = [e for e in elements.values()
            if e['cost_change_event'] < 0 and float(e['selected_by_percent']) >= 5]
    if rise or fall:
        L.append('\n<b>Price moves this week</b> <i>(5%+ owned)</i>')
        if rise:
            L.append('↑ ' + ', '.join('%s £%.1f' % (_esc(e['web_name']), e['now_cost'] / 10)
                                       for e in rise[:6]))
        if fall:
            L.append('↓ ' + ', '.join('%s £%.1f' % (_esc(e['web_name']), e['now_cost'] / 10)
                                       for e in fall[:6]))
    L.append('\nhttp://fpl.salwood.co.za')
    return '\n'.join(L)


def maybe_notify(elements, teams, news_payload, hours=6, force=False, owned=None,
                 events=None):
    """Two things get pushed, and nothing else.

    An injury or rotation risk to a player the reader OWNS goes out the same day,
    because that is the only news that cannot wait for Friday. Everything else
    waits for one post a week, a day before the deadline, which is when the
    decision actually gets made.
    """
    tok, chat = creds()
    if not tok or not chat:
        return 'unconfigured'
    hour = _uk_now().hour
    if not force and (hour >= QUIET_FROM or hour < QUIET_TO):
        return 'quiet hours'
    st = _state()
    seen = set(st.get('sent', []))
    owned = set(owned or ())
    did = []

    # --- the exception: your own players, same day --------------------------
    if owned and news_payload:
        alerts, akeys = urgent_squad_alerts(news_payload, owned, seen)
        if alerts:
            body = '<b>Fleamarket</b> · your squad\n\n' + '\n\n'.join(alerts[:4])
            if send(body):
                st['sent'] = list(st.get('sent', [])) + akeys
                seen |= set(akeys)
                did.append('%d squad alert(s)' % len(alerts[:4]))

    # --- the weekly post ----------------------------------------------------
    ev, left = deadline_window(events)
    if ev and left is not None:
        # First cycle that falls inside the lead time sends, and the gameweek
        # stamp stops it repeating. If cycles were missed it goes out whenever
        # the loop next runs - late is still better than never, since the team
        # can be changed right up to the deadline.
        inside = 0 < left <= DIGEST_LEAD_HOURS
        if force or (inside and st.get('digest_gw') != ev['id']):
            tp = None
            try:
                tp = json.load(open('bootstrap.json', encoding='utf-8')).get('total_players')
            except Exception:  # noqa: BLE001
                pass
            text = weekly_digest(elements, teams, ev, left, owned, tp)
            if text and send(text):
                st['digest_gw'] = ev['id']
                did.append('GW%d digest' % ev['id'])

    if did:
        st['sent'] = list(st.get('sent', []))[-400:]
        st['last'] = _uk_now().isoformat(timespec='minutes')
        _save_state(st)
        return 'sent: ' + ', '.join(did)
    return 'nothing due'


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
