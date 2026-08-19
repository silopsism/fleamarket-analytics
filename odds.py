"""Bookmaker odds → per-fixture expected goals.

Source: football-data.co.uk/fixtures.csv (free, no key, market-average odds).
From over/under 2.5 we recover the total expected goals in a match; the Asian
handicap line gives the expected goal difference. Together they pin down each
team's expected goals — a continuous signal, unlike FPL's four-notch difficulty
rating.

Writes odds_cache.json: {ts, fixtures: [{event, home, away, lh, la}],
teams: {"ARS": {"3": {"gf": 2.1, "ga": 0.7, "home": 1}}}}
Absent or stale data simply means the model keeps using its FDR heuristic.
"""
import csv
import io
import json
import math
import urllib.request
from datetime import datetime, timezone

URL = 'https://www.football-data.co.uk/fixtures.csv'
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}
LEAGUE_AVG_GOALS = 1.45          # per team per match, recent PL seasons

# football-data spellings that differ from FPL's team names
ALIAS = {
    'Man City': 'Man City', 'Man United': 'Man Utd', 'Man Utd': 'Man Utd',
    "Nott'm Forest": "Nott'm Forest", 'Nottingham': "Nott'm Forest",
    'Tottenham': 'Spurs', 'Spurs': 'Spurs', 'Newcastle': 'Newcastle',
    'Wolves': 'Wolves', 'Sheffield United': 'Sheffield Utd',
    'Leeds': 'Leeds', 'Ipswich': 'Ipswich', 'Coventry': 'Coventry',
    'Hull': 'Hull', 'Brighton': 'Brighton', 'West Ham': 'West Ham',
    'Crystal Palace': 'Crystal Palace', 'Aston Villa': 'Aston Villa',
}


def _devig(o1, o2):
    """Two-way market → fair probability of the first outcome."""
    try:
        i1, i2 = 1.0 / float(o1), 1.0 / float(o2)
        return i1 / (i1 + i2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _lambda_from_over(p_over, line=2.5):
    """Total expected goals implied by P(total > line), assuming Poisson."""
    if not p_over or not 0.02 < p_over < 0.98:
        return None
    k_max = int(math.floor(line))

    def p_over_for(lam):
        under = sum(math.exp(-lam) * lam ** k / math.factorial(k) for k in range(k_max + 1))
        return 1 - under

    lo, hi = 0.2, 7.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if p_over_for(mid) < p_over:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


def fetch(fixtures_path='fixtures.json', bootstrap_path='bootstrap.json',
          out='odds_cache.json', div='E0'):
    """Pull the odds sheet and translate it into per-team expected goals by
    gameweek. Returns the payload (also written to `out`)."""
    req = urllib.request.Request(URL, headers=UA)
    raw = urllib.request.urlopen(req, timeout=25).read().decode('utf-8-sig', 'ignore')
    rows = list(csv.DictReader(io.StringIO(raw)))

    boot = json.load(open(bootstrap_path, encoding='utf-8'))
    fpl_names = {t['name']: t['short_name'] for t in boot['teams']}
    fx = json.load(open(fixtures_path, encoding='utf-8'))
    id2short = {t['id']: t['short_name'] for t in boot['teams']}
    # (home_short, away_short) -> event, so we can label each odds row
    pair2event = {}
    for f in fx:
        if f['event']:
            pair2event[(id2short[f['team_h']], id2short[f['team_a']])] = f['event']

    def short(name):
        name = (name or '').strip()
        mapped = ALIAS.get(name, name)
        return fpl_names.get(mapped, mapped if mapped in id2short.values() else None)

    out_fx, teams = [], {}
    for r in rows:
        if (r.get('Div') or '').strip() != div:
            continue
        h, a = short(r.get('HomeTeam')), short(r.get('AwayTeam'))
        if not h or not a:
            continue
        p_over = _devig(r.get('Avg>2.5') or r.get('B365>2.5'),
                        r.get('Avg<2.5') or r.get('B365<2.5'))
        total = _lambda_from_over(p_over)
        try:
            ahh = float(r.get('AHh'))
        except (TypeError, ValueError):
            ahh = None
        if total is None or ahh is None:
            continue
        sup = -ahh                       # expected goal difference, home minus away
        lh, la = (total + sup) / 2, (total - sup) / 2
        if min(lh, la) <= 0.05:
            continue
        ev = pair2event.get((h, a))
        rec = {'event': ev, 'home': h, 'away': a,
               'lh': round(lh, 2), 'la': round(la, 2), 'total': total}
        out_fx.append(rec)
        if ev:
            teams.setdefault(h, {})[str(ev)] = {'gf': rec['lh'], 'ga': rec['la'], 'home': 1}
            teams.setdefault(a, {})[str(ev)] = {'gf': rec['la'], 'ga': rec['lh'], 'home': 0}

    payload = {'ts': datetime.now(timezone.utc).isoformat(timespec='minutes'),
               'league_avg': LEAGUE_AVG_GOALS, 'fixtures': out_fx, 'teams': teams,
               'rows_seen': len(rows)}
    json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return payload


def load(path='odds_cache.json'):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return None


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'math':
        # prove the derivation on any league present in today's sheet
        raw = urllib.request.urlopen(urllib.request.Request(URL, headers=UA),
                                     timeout=25).read().decode('utf-8-sig', 'ignore')
        for r in list(csv.DictReader(io.StringIO(raw))):
            p_over = _devig(r.get('Avg>2.5') or r.get('B365>2.5'),
                            r.get('Avg<2.5') or r.get('B365<2.5'))
            tot = _lambda_from_over(p_over)
            try:
                ahh = float(r.get('AHh'))
            except (TypeError, ValueError):
                ahh = None
            if tot and ahh is not None:
                lh, la = (tot - ahh) / 2, (tot + ahh) / 2
                print(f"{r['Div']} {r['HomeTeam']} v {r['AwayTeam']}: "
                      f"P(o2.5)={p_over:.2f} total={tot:.2f} AHh={ahh} → "
                      f"{lh:.2f} - {la:.2f}")
    else:
        p = fetch()
        print(f"odds: {len(p['fixtures'])} PL fixtures priced "
              f"(sheet had {p['rows_seen']} rows)")
        for f in p['fixtures'][:10]:
            print(f"  GW{f['event']} {f['home']} {f['lh']:.2f} - {f['la']:.2f} {f['away']}")
