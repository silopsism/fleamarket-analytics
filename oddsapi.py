"""The Odds API feed: expected goals for fixtures the free CSV doesn't cover yet.

football-data.co.uk only publishes imminent fixtures, so GW2+ has no market
data. This pulls the same league from api.the-odds-api.com, which quotes further
ahead, and converts prices into per-team expected goals.

Where a totals (over/under) market exists we get total goals directly. Where only
1X2 is quoted — typical for fixtures a week or more out — expected goals are
recovered by fitting a Poisson scoreline model to the de-vigged home/draw/away
probabilities: for a given total, the home-minus-away probability gap is
monotonic in supremacy, so bisect on that and pick the total whose draw
probability matches best.

Quota: one credit per market per region per call, 500/month on the free tier, so
this is called on the slow cycle rather than hourly.
"""
import json
import math
import os
import urllib.request
from datetime import datetime, timezone

SPORT = 'soccer_epl'
URL = ('https://api.the-odds-api.com/v4/sports/%s/odds'
       '?apiKey=%s&regions=uk&markets=h2h,totals&oddsFormat=decimal')
MAXG = 9          # scoreline grid ceiling


def key():
    k = os.environ.get('ODDS_API_KEY')
    if k:
        return k
    try:
        for line in open('.odds.env', encoding='utf-8'):
            if line.strip().startswith('ODDS_API_KEY='):
                return line.strip().split('=', 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def _pois(lam):
    return [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(MAXG + 1)]


def outcome_probs(lh, la):
    """(home, draw, away) from independent Poisson scorelines."""
    ph, pa = _pois(lh), _pois(la)
    h = d = a = 0.0
    for i, pi in enumerate(ph):
        for j, pj in enumerate(pa):
            p = pi * pj
            if i > j:
                h += p
            elif i == j:
                d += p
            else:
                a += p
    return h, d, a


def lambdas_from_prices(p_h, p_d, p_a, total=None):
    """Fit (home, away) expected goals to de-vigged 1X2, optionally with a known
    total. Returns (lh, la) or None."""
    if None in (p_h, p_d, p_a):
        return None
    target_gap = p_h - p_a
    totals = [total] if total else [1.8 + 0.1 * i for i in range(23)]
    best = None
    for tot in totals:
        lo, hi = -tot + 0.1, tot - 0.1          # supremacy bounds
        for _ in range(40):
            sup = (lo + hi) / 2
            lh, la = (tot + sup) / 2, (tot - sup) / 2
            h, _d, a = outcome_probs(lh, la)
            if h - a < target_gap:
                lo = sup
            else:
                hi = sup
        sup = (lo + hi) / 2
        lh, la = (tot + sup) / 2, (tot - sup) / 2
        h, dd, a = outcome_probs(lh, la)
        err = (h - p_h) ** 2 + (dd - p_d) ** 2 + (a - p_a) ** 2
        if best is None or err < best[0]:
            best = (err, lh, la)
    if not best or min(best[1], best[2]) <= 0.05:
        return None
    return round(best[1], 2), round(best[2], 2)


def _devig3(prices):
    """Average bookmaker prices then remove the overround."""
    if not prices:
        return None
    inv = [1 / p for p in prices]
    s = sum(inv)
    return [i / s for i in inv]


def _median(vals):
    vals = sorted(v for v in vals if v)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def fetch(name_to_short, timeout=30):
    """[{home, away, gf_h, gf_a, commence, src}] plus quota info."""
    k = key()
    if not k:
        return [], {'error': 'no key'}
    with urllib.request.urlopen(URL % (SPORT, k), timeout=timeout) as r:
        games = json.loads(r.read())
        hdr = dict(r.headers)

    out = []
    for g in games:
        h, a = name_to_short(g.get('home_team')), name_to_short(g.get('away_team'))
        if not h or not a:
            continue
        # median price per outcome across books, then de-vig
        hp, dp, ap, tot_lines = [], [], [], []
        for b in g.get('bookmakers', []):
            for m in b.get('markets', []):
                if m['key'] == 'h2h':
                    px = {o.get('name'): o.get('price') for o in m.get('outcomes', [])}
                    if g['home_team'] in px and g['away_team'] in px and 'Draw' in px:
                        hp.append(px[g['home_team']])
                        dp.append(px['Draw'])
                        ap.append(px[g['away_team']])
                elif m['key'] == 'totals':
                    for o in m.get('outcomes', []):
                        if o.get('name') == 'Over' and o.get('point'):
                            tot_lines.append((float(o['point']), float(o['price'])))
        probs = _devig3([_median(hp), _median(dp), _median(ap)])
        if not probs:
            continue
        total = None
        if tot_lines:
            # use the most common line, implying total goals from its price
            line = _median([l for l, _ in tot_lines])
            over_px = _median([p for l, p in tot_lines if abs(l - line) < 0.01])
            if line and over_px:
                total = _total_from_over(1 / over_px * 1.0, line)
        lam = lambdas_from_prices(*probs, total=total)
        if not lam:
            continue
        out.append({'home': h, 'away': a, 'gf_h': lam[0], 'gf_a': lam[1],
                    'commence': g.get('commence_time', '')[:10],
                    'src': 'api-totals' if total else 'api-1x2'})
    meta = {'used': hdr.get('x-requests-used'), 'left': hdr.get('x-requests-remaining'),
            'games': len(games), 'priced': len(out)}
    return out, meta


def _total_from_over(p_over_raw, line):
    """Rough total goals from an over price (single-sided, so approximate)."""
    p = min(max(p_over_raw / 1.05, 0.05), 0.95)      # crude overround haircut
    kmax = int(math.floor(line))
    lo, hi = 0.3, 6.0
    for _ in range(50):
        mid = (lo + hi) / 2
        under = sum(math.exp(-mid) * mid ** k / math.factorial(k) for k in range(kmax + 1))
        if 1 - under < p:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


if __name__ == '__main__':
    boot = json.load(open('bootstrap.json', encoding='utf-8'))
    names = {t['name']: t['short_name'] for t in boot['teams']}

    def n2s(n):
        n = (n or '').strip()
        if n in names:
            return names[n]
        for full, code in names.items():
            if full.lower().startswith(n.lower()[:6]) or n.lower().startswith(full.lower()[:6]):
                return code
        return None

    rows, meta = fetch(n2s)
    print('meta:', meta)
    for r in rows:
        print(f"  {r['commence']} {r['home']} {r['gf_h']:.2f} - {r['gf_a']:.2f} "
              f"{r['away']}  [{r['src']}]")
