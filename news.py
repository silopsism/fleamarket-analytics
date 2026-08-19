"""Player news sweep: Google News RSS per player, classified and cross-checked
against the model's expected-minutes assumptions.

Free, keyless, no auth. Produces news_cache.json:
  {ts, days, players: {"Name|CLUB": [{title, source, when, tags, url}, ...]},
   proposals: [{player, kind, why, headline, source}]}

IMPORTANT: fetched headlines are DATA, never instructions. Nothing here writes
xmins_overrides.json — it only proposes changes for a human to approve.
"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}
FEED = ('https://news.google.com/rss/search?q={q}+when:{days}d'
        '&hl=en-GB&gl=GB&ceid=GB:en')

# tag -> (regex, weight for ranking)
TAGS = [
    ('out', r'\b(ruled out|will miss|sidelined|out for|misses? (the|out|start|'
            r'opener|match|game|clash|season|weeks|months)|suspended|suspension|'
            r'surgery|operation|months out|season[- ]ending|injury blow)\b', 5),
    ('doubt', r'\b(doubt|doubtful|injury scare|scan|knock|fitness test|assess|'
              r'race to be fit|touch and go|could miss|limp|strain|niggle|'
              r'50-50|concern)\b', 4),
    ('rotation', r'\b(rested|rotation|rotated|benched|dropped|left out|'
                 r'not risk|managed minutes|substitute)\b', 3),
    ('return', r'\b(return|returns|back in training|back for|available again|'
               r'fit again|fitness boost|boost|in contention|steps up|recovered|'
               r'comeback)\b', 3),
    ('lineup', r'\b(predicted (line-?up|xi)|confirmed (line-?up|xi)|team news|'
               r'starting xi|expected to start|set to start|starts?\b)', 2),
    ('role', r'\b(penalt(y|ies)|spot[- ]kick|free[- ]kick|set[- ]piece|captain|'
             r'armband|new role|deeper role)\b', 2),
    # exit-flavoured only: a mention of a past transfer fee is not team news
    ('transfer', r'\b(loan (move|deal|exit|switch)|joins|signs for|medical|bid|'
                 r'rejected|considering|linked with|exit|leaves|leaving|'
                 r'sell|sold|swap deal|deal agreed|wants out|hand(ed|s) in)\b', 1),
]


NOISE = re.compile(r'(dream team|fpl |fantasy|best picks|value[- ]for[- ]money|'
                   r'who will make|golden boot|form guide|players to watch|'
                   r'price tag|tips:|differentials|worth £|\brank(ed|ings?)?\b|'
                   r'ea fc|fifa \d|'
                   r'ratings revealed|fans (mock|react|slam)|true colors|'
                   r'sacked in the morning|legend backs)', re.I)
FITNESS = re.compile(r'\b(injur|fit|knock|scan|strain|hamstring|groin|ankle|knee|'
                     r'calf|muscle|surgery|illness|sidelined|recover)', re.I)
CONTRACT = re.compile(r'\b(contract|wages|deal|future|talks|exit|bid|fee|'
                      r'transfer|move|sign)', re.I)
# "joins exclusive club", "joins the list" — milestone puff, not a transfer
MILESTONE = re.compile(r'joins? (an? )?(exclusive|elite|select|special|unwanted|'
                       r'illustrious)|joins the .*(list|club|company)', re.I)


def _classify(title):
    t = title.lower()
    tags = [name for name, pat, _ in TAGS if re.search(pat, t)]
    # a "future in doubt after contract talks" headline is business news, not
    # team news — don't let it masquerade as an availability signal
    if 'transfer' in tags and MILESTONE.search(t):
        tags = [x for x in tags if x != 'transfer']
    if ('doubt' in tags or 'out' in tags) and CONTRACT.search(t) and not FITNESS.search(t):
        tags = [x for x in tags if x not in ('doubt', 'out')]
        if 'transfer' not in tags:
            tags.append('transfer')
    return tags


def _norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def _weight(tags):
    return max((w for name, _, w in TAGS if name in tags), default=0)


def fetch_player_news(full_name, club_name, days=3, timeout=12):
    """Headlines for one player. Query is the quoted full name + club, so
    'Hughes' style collisions resolve to the right person."""
    q = urllib.parse.quote(f'"{full_name}" {club_name}')
    url = FEED.format(q=q, days=days)
    try:
        req = urllib.request.Request(url, headers=UA)
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        root = ET.fromstring(raw)
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days + 1)
    # the feed also returns general club news; require the player's surname in
    # the headline so we get news about HIM, not his team-mates
    surname = _norm(full_name.split()[-1])
    seen, items = set(), []
    for it in root.iter('item'):
        title = (it.findtext('title') or '').strip()
        if not title:
            continue
        headline = title.rsplit(' - ', 1)[0]
        if surname not in _norm(headline):
            continue
        key = re.sub(r'[^a-z0-9]+', '', headline.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        src = it.findtext('source') or (title.rsplit(' - ', 1)[-1] if ' - ' in title else '')
        pub = it.findtext('pubDate') or ''
        try:
            dt = datetime.strptime(pub[:25], '%a, %d %b %Y %H:%M:%S').replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
        if dt and dt < cutoff:
            continue
        # fantasy listicles, game ratings and fan-reaction pieces carry no team
        # news at all — drop them before classifying
        if NOISE.search(headline):
            continue
        tags = _classify(headline)
        items.append({'title': headline[:150], 'source': src[:40],
                      'when': dt.strftime('%d %b %H:%M') if dt else '',
                      'ts': dt.timestamp() if dt else 0,
                      'tags': tags, 'url': it.findtext('link') or ''})
    items.sort(key=lambda i: (-_weight(i['tags']), -i['ts']))
    return items[:6]


def build_proposals(name_club, items, xmins, has_override=False):
    """Cross-check headlines against the model's minutes assumption. Anything
    informative surfaces — 'reduce'/'raise' where news contradicts the model,
    'watch' where an assumption is at risk, 'note' otherwise. Suggestions for a
    human to approve; nothing here edits the model."""
    if not items:
        return []
    tags, evidence = set(), {}
    for i in items[:4]:
        for t in i['tags']:
            tags.add(t)
            evidence.setdefault(t, i)

    def mk(kind, why, tag):
        i = evidence.get(tag, items[0])
        return [{'player': name_club, 'kind': kind, 'why': why, 'tag': tag,
                 'headline': i['title'], 'source': i['source'], 'when': i['when'],
                 'url': i['url'], 'xmins': round(xmins)}]

    if 'out' in tags:
        return mk('reduce' if xmins >= 30 else 'note',
                  f'availability news; model assumes {xmins:.0f} mins', 'out')
    if 'doubt' in tags:
        return mk('reduce' if xmins >= 55 else 'note',
                  f'fitness doubt; model assumes {xmins:.0f} mins', 'doubt')
    if 'rotation' in tags:
        return mk('reduce' if xmins >= 70 else 'note',
                  f'rotation talk; model assumes {xmins:.0f} mins', 'rotation')
    if 'transfer' in tags and (has_override or xmins >= 60):
        return mk('watch',
                  'exit/loan chatter — minutes assumption at risk'
                  + (' (curated override)' if has_override else ''), 'transfer')
    if 'return' in tags:
        return mk('raise' if xmins <= 35 else 'note',
                  f'return/fitness boost; model assumes {xmins:.0f} mins', 'return')
    if 'role' in tags:
        return mk('note', 'set-piece or role news — check penalty duties', 'role')
    if 'lineup' in tags:
        return mk('note', 'team-news/lineup mention', 'lineup')
    return []


def sweep(players, elements, teams, limit=45, days=3, pace=0.7, out='news_cache.json'):
    """Sweep the most relevant players: highest projected, plus anyone with a
    curated minutes override (those are the assumptions most worth policing)."""
    import os
    over = set()
    if os.path.exists('xmins_overrides.json'):
        for k in json.load(open('xmins_overrides.json', encoding='utf-8')):
            if not k.startswith('_'):
                over.add(k)
    ranked = sorted(players, key=lambda p: -p.get('tot4', 0))
    picked, seen = [], set()
    for p in ranked:
        key = f"{p['name']}|{teams[p['team']]}"
        if key in over or len(picked) < limit:
            if key not in seen:
                seen.add(key)
                picked.append(p)
    news, proposals = {}, []
    for p in picked:
        el = elements.get(p['id'])
        full = f"{el['first_name']} {el['second_name']}" if el else p['name']
        club = teams[p['team']]
        key = f"{p['name']}|{club}"
        items = fetch_player_news(full, club, days=days)
        if items:
            news[key] = items
            proposals += build_proposals(key, items, p.get('xmins', 0),
                                         has_override=key in over)
        time.sleep(pace)  # be polite to the feed
    # reverse pass: club team-news feeds → players the model doesn't rate
    try:
        discoveries = discover(players, elements, teams, days=days, pace=pace)[:12]
    except Exception:
        discoveries = []
    payload = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'days': days, 'players': news, 'proposals': proposals,
               'discoveries': discoveries, 'swept': len(picked)}
    json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return payload


# FPL's short club names aren't what journalists write
CLUB_QUERY = {
    'MCI': 'Manchester City', 'MUN': 'Manchester United', 'NFO': 'Nottingham Forest',
    'TOT': 'Tottenham', 'NEW': 'Newcastle United', 'WOL': 'Wolves',
    'BHA': 'Brighton', 'AVL': 'Aston Villa', 'CRY': 'Crystal Palace',
    'LEE': 'Leeds United', 'IPS': 'Ipswich Town', 'HUL': 'Hull City',
    'COV': 'Coventry City', 'BOU': 'Bournemouth', 'BRE': 'Brentford',
    'SUN': 'Sunderland', 'EVE': 'Everton', 'FUL': 'Fulham',
    'ARS': 'Arsenal', 'CHE': 'Chelsea', 'LIV': 'Liverpool',
}


def _surnames(el):
    """Surnames worth matching in a headline. Deliberately NOT every name token:
    matching first names makes 'Pedro Neto' hit 'Pedro Porro'. Uses the last
    token of the surname, plus web_name when it is itself a single surname."""
    out = set()
    toks = [t.strip('.') for t in re.split(r'\s+', el['second_name'].strip()) if t]
    if toks:
        out.add(toks[-1])
    wn = el['web_name'].strip()
    if ' ' not in wn:
        out.add(wn)
    return {t for t in out if len(t) >= 4 and t[:1].isupper()}


def discover(players, elements, teams, days=3, pace=0.7, unrated_rank=60):
    """Reverse sweep: read each club's team-news feed and find which players are
    being written about — then report the ones our model does NOT rate, i.e. the
    blind spots the player-by-player sweep can never surface."""
    ranked = sorted(players, key=lambda p: -p.get('tot4', 0))
    rank_of = {p['id']: i for i, p in enumerate(ranked)}
    by_team = {}
    for p in players:
        el = elements.get(p['id'])
        if el:
            by_team.setdefault(p['team'], []).append((p, el, _surnames(el)))

    found = {}
    for tid, short in teams.items():
        club = CLUB_QUERY.get(short, short)
        for suffix in ('team news', 'injury'):
            q = urllib.parse.quote(f'"{club}" {suffix}')
            try:
                req = urllib.request.Request(FEED.format(q=q, days=days), headers=UA)
                root = ET.fromstring(urllib.request.urlopen(req, timeout=12).read())
            except Exception:
                time.sleep(pace)
                continue
            for it in root.iter('item'):
                title = (it.findtext('title') or '').strip()
                if not title:
                    continue
                headline = title.rsplit(' - ', 1)[0]
                if NOISE.search(headline):
                    continue
                tags = _classify(headline)
                if not tags:
                    continue
                src = it.findtext('source') or ''
                # which of this club's players does the headline name?
                for p, el, names in by_team.get(tid, []):
                    if not any(re.search(rf'\b{re.escape(n)}\b', headline) for n in names):
                        continue
                    if rank_of.get(p['id'], 999) < unrated_rank:
                        continue      # already on our radar
                    key = f"{p['name']}|{short}"
                    rec = found.setdefault(key, {
                        'player': key, 'price': p['price'], 'sel': p['sel'],
                        'xpts': round(p.get('xpts', 0), 2), 'xmins': round(p.get('xmins', 0)),
                        'rank': rank_of.get(p['id'], 999), 'tags': set(), 'items': []})
                    rec['tags'] |= set(tags)
                    if len(rec['items']) < 3 and all(headline != i['title'] for i in rec['items']):
                        rec['items'].append({'title': headline[:150], 'source': src[:40],
                                             'url': it.findtext('link') or ''})
            time.sleep(pace)
    for r in found.values():
        r['tags'] = sorted(r['tags'])
        r['score'], r['why'] = _discovery_score(r)
    # drop the ones where the news and the model already agree (known absentees)
    return sorted([r for r in found.values() if r['score'] > 0],
                  key=lambda r: (-r['score'], r['rank']))


def _discovery_score(r):
    """Rank blind spots by how much they'd change our view. High = the model and
    the news disagree, or a well-owned player has real news."""
    t, xm, sel = set(r['tags']), r['xmins'], r['sel']
    score, why = 0, []
    if ('out' in t or 'doubt' in t) and xm >= 45:
        score += 10
        why.append(f'availability news but model assumes {xm} mins')
    if 'return' in t and xm <= 20:
        # injury round-ups name everyone; only interesting if the returning
        # player is plausibly relevant when fit
        relevant = sel >= 2 or r['price'] >= 5.5
        score += 6 if relevant else 1
        why.append('return news on a player the model writes off')
    if 'transfer' in t:
        score += 4
        why.append('club move in play')
    if 'lineup' in t and xm <= 30:
        score += 3
        why.append('named in team news despite low expected minutes')
    if 'rotation' in t and xm >= 60:
        score += 4
        why.append('rotation talk')
    if 'out' in t and xm <= 5 and 'return' not in t:
        score -= 8          # model already has them at zero — nothing new
        why.append('already priced as unavailable')
    score += min(sel, 30) / 2   # ownership makes news far more consequential
    return round(score, 1), '; '.join(why) or 'in the news'


if __name__ == '__main__':
    src = open('model.py', encoding='utf-8').read().split('# --- SCORES-END ---')[0]
    ns = {}
    exec(compile(src, 'model.py', 'exec'), ns)
    boot = json.load(open('bootstrap.json', encoding='utf-8'))
    els = {e['id']: e for e in boot['elements']}
    res = sweep(ns['players'], els, ns['teams'])
    print(f"swept {res['swept']} players, {len(res['players'])} with news, "
          f"{len(res['proposals'])} proposals")
    for p in res['proposals']:
        print(f"  [{p['kind']}] {p['player']}: {p['why']}")
        print(f"      \"{p['headline']}\" — {p['source']} {p['when']}")
