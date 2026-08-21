"""One club-name resolver for every external source.

Wikipedia, football-data.co.uk and The Odds API each spell clubs differently
("Man Utd" / "Manchester United", "Spurs" / "Tottenham Hotspur", "Coventry" /
"Coventry City"), and silently dropping a row because of it has already cost us
three separate bugs — including both fixtures that mattered for a captaincy call.

resolve(name, boot) returns an FPL short code or None, trying: exact short code,
exact FPL name, a hand-written alias table, then distinctive-token overlap.
"""
import re
import unicodedata

# any spelling -> the distinctive token(s) we expect in an FPL club name
ALIASES = {
    'man utd': 'MUN', 'man united': 'MUN', 'manchester united': 'MUN',
    'man city': 'MCI', 'manchester city': 'MCI',
    'spurs': 'TOT', 'tottenham': 'TOT', 'tottenham hotspur': 'TOT',
    'nottm forest': 'NFO', 'nott m forest': 'NFO', 'nottingham': 'NFO',
    'nottingham forest': 'NFO', 'forest': 'NFO',
    'wolves': 'WOL', 'wolverhampton': 'WOL', 'wolverhampton wanderers': 'WOL',
    'west ham': 'WHU', 'west ham united': 'WHU',
    'newcastle': 'NEW', 'newcastle united': 'NEW',
    'brighton': 'BHA', 'brighton and hove albion': 'BHA',
    'brighton hove albion': 'BHA',
    'leeds': 'LEE', 'leeds united': 'LEE',
    'ipswich': 'IPS', 'ipswich town': 'IPS',
    'coventry': 'COV', 'coventry city': 'COV',
    'hull': 'HUL', 'hull city': 'HUL',
    'bournemouth': 'BOU', 'afc bournemouth': 'BOU',
    'sheffield united': 'SHU', 'sheffield utd': 'SHU',
    'luton': 'LUT', 'luton town': 'LUT',
    'leicester': 'LEI', 'leicester city': 'LEI',
    'southampton': 'SOU', 'norwich': 'NOR', 'norwich city': 'NOR',
    'burnley': 'BUR', 'sunderland': 'SUN', 'everton': 'EVE',
    'fulham': 'FUL', 'brentford': 'BRE', 'chelsea': 'CHE', 'arsenal': 'ARS',
    'liverpool': 'LIV', 'aston villa': 'AVL', 'crystal palace': 'CRY',
}
STOP = {'fc', 'afc', 'united', 'city', 'town', 'albion', 'wanderers', 'hotspur',
        'and', 'hove', 'the'}


def _norm(s):
    s = unicodedata.normalize('NFKD', (s or '').lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]', ' ', s).strip()


def _tokens(s):
    return {t for t in _norm(s).split() if t and t not in STOP}


def resolve(name, boot):
    """Map any spelling of a club to its FPL short code, or None."""
    if not name:
        return None
    shorts = {t['short_name'] for t in boot['teams']}
    by_name = {_norm(t['name']): t['short_name'] for t in boot['teams']}

    raw = name.strip()
    if raw.upper() in shorts:
        return raw.upper()
    n = _norm(raw)
    if n in by_name:
        return by_name[n]
    alias = ALIASES.get(n)
    if alias and alias in shorts:
        return alias
    # distinctive-token overlap, e.g. "Nottingham Forest" -> "Nott'm Forest"
    want = _tokens(raw)
    if want:
        best, score = None, 0
        for full, code in by_name.items():
            have = _tokens(full)
            hit = len(want & have)
            # allow prefix matches on the distinctive token (nottingham/nott m)
            if not hit:
                hit = sum(1 for a in want for b in have
                          if len(a) >= 4 and len(b) >= 4
                          and (a.startswith(b[:4]) or b.startswith(a[:4])))
            if hit > score:
                best, score = code, hit
        if best and score:
            return best
    return None


def resolver(boot):
    """Cached single-argument resolver for a given bootstrap."""
    cache = {}

    def f(name):
        if name not in cache:
            cache[name] = resolve(name, boot)
        return cache[name]
    return f
