"""Summer transfer ledger, parsed from Wikipedia's English football transfers list.

The FPL API has no fees and no record of departures — players who leave simply
vanish from it — so the ins/outs and net spend come from Wikipedia's list, which
tags fees numerically ({{ntsh|34500000}}) alongside the display text.

Writes transfers_cache.json: {ts, clubs: {"ARS": {in: [...], out: [...],
spend, received, net}}, unmatched}
"""
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PAGE = 'List_of_English_football_transfers_summer_2026'
API = ('https://en.wikipedia.org/w/api.php?action=parse&page=%s'
       '&prop=wikitext&format=json&formatversion=2')
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}

# Wikipedia display names -> FPL short names
CLUBS = {
    'Arsenal': 'ARS', 'Aston Villa': 'AVL', 'Bournemouth': 'BOU',
    'AFC Bournemouth': 'BOU', 'Brentford': 'BRE', 'Brighton & Hove Albion': 'BHA',
    'Brighton and Hove Albion': 'BHA', 'Chelsea': 'CHE', 'Coventry City': 'COV',
    'Crystal Palace': 'CRY', 'Everton': 'EVE', 'Fulham': 'FUL', 'Hull City': 'HUL',
    'Ipswich Town': 'IPS', 'Leeds United': 'LEE', 'Liverpool': 'LIV',
    'Manchester City': 'MCI', 'Manchester United': 'MUN', 'Newcastle United': 'NEW',
    'Nottingham Forest': 'NFO', 'Tottenham Hotspur': 'TOT', 'Sunderland': 'SUN',
}


def _clean(cell):
    """Reduce a wikitext cell to plain text."""
    s = cell
    s = re.sub(r'<ref[^>]*>.*?</ref>', '', s, flags=re.S)
    s = re.sub(r'<ref[^>]*/>', '', s)
    s = re.sub(r'\{\{[Ff]lagg?\|[^}]*\}\}', '', s)
    s = re.sub(r'\{\{ntsh\|[^}]*\}\}', '', s)
    s = re.sub(r'\{\{[Ss]ortname\|([^|}]*)\|([^|}]*)(\|[^}]*)?\}\}', r'\1 \2', s)
    s = re.sub(r'\[\[[^\]|]*\|([^\]]*)\]\]', r'\1', s)
    s = re.sub(r'\[\[([^\]]*)\]\]', r'\1', s)
    s = re.sub(r'\{\{[^}]*\}\}', '', s)
    s = re.sub(r"'''?", '', s)
    return re.sub(r'\s+', ' ', s).strip()


def _fee(cell):
    """(numeric_fee_or_None, label). ntsh carries the sortable numeric value."""
    m = re.search(r'\{\{ntsh\|(\d+)\}\}', cell)
    txt = _clean(cell)
    val = None
    if m:
        n = int(m.group(1))
        if n > 1000:                      # 1 is the placeholder for undisclosed
            val = n
    if val is None:
        m2 = re.search(r'£([\d.]+)\s*(m|million)', txt, re.I)
        if m2:
            val = int(float(m2.group(1)) * 1_000_000)
    return val, (txt[:40] or 'Undisclosed')


def fetch(out='transfers_cache.json', bootstrap_path='bootstrap.json'):
    import clubs
    _boot = json.load(open(bootstrap_path, encoding='utf-8'))
    _res = clubs.resolver(_boot)
    url = API % PAGE
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
    wt = json.loads(raw)['parse']['wikitext']

    clubs = {c: {'in': [], 'out': [], 'spend': 0, 'received': 0} for c in set(CLUBS.values())}
    unmatched, rows_seen = 0, 0
    for block in wt.split('\n|-')[1:]:
        block = block.split('\n|}')[0]
        cells = re.split(r'\n\|(?!\})', block)
        cells = [c for c in cells if c.strip()]
        if len(cells) < 3:
            continue
        # schema is Player | Moving from | Moving to | Fee, sometimes with a
        # leading date and, for loans, a trailing "until" column — so anchor on
        # the FIRST cells after dropping any leading date
        while cells and re.match(r'^\s*\|?\s*(\d{1,2}\s+\w+\s+\d{4}|\{\{dts)',
                                 cells[0].strip()):
            cells = cells[1:]
        if len(cells) < 4:
            continue
        player, frm, to, feecell = cells[0], cells[1], cells[2], cells[3]
        name, a, b = _clean(player), _clean(frm), _clean(to)
        if not name or re.match(r'^\d{1,2} \w+ \d{4}$', name):
            continue
        rows_seen += 1
        val, label = _fee(feecell)
        ca, cb = _res(a), _res(b)
        loan = 'loan' in label.lower()
        if cb:
            clubs[cb]['in'].append({'name': name, 'other': a, 'fee': val,
                                    'label': label, 'loan': loan})
            if val and not loan:
                clubs[cb]['spend'] += val
        if ca:
            clubs[ca]['out'].append({'name': name, 'other': b, 'fee': val,
                                     'label': label, 'loan': loan})
            if val and not loan:
                clubs[ca]['received'] += val
        if not ca and not cb:
            unmatched += 1
    for c in clubs.values():
        c['net'] = c['spend'] - c['received']
        c['in'].sort(key=lambda x: -(x['fee'] or 0))
        c['out'].sort(key=lambda x: -(x['fee'] or 0))

    payload = {'ts': datetime.now(timezone.utc).isoformat(timespec='minutes'),
               'source': 'Wikipedia: ' + PAGE.replace('_', ' '),
               'clubs': clubs, 'rows_seen': rows_seen, 'unmatched': unmatched}
    json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return payload


def load(path='transfers_cache.json'):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return None


if __name__ == '__main__':
    p = fetch()
    print(f"rows parsed: {p['rows_seen']}, non-PL rows: {p['unmatched']}")
    rows = sorted(p['clubs'].items(), key=lambda kv: -kv[1]['net'])
    for c, d in rows:
        print(f"{c:4} in={len(d['in']):2} out={len(d['out']):2} "
              f"spend=£{d['spend']/1e6:6.1f}m received=£{d['received']/1e6:6.1f}m "
              f"net=£{d['net']/1e6:+7.1f}m")
