"""Local cache of the official FPL kit images.

Hand-drawn SVG shirts were never going to look right: twenty clubs have real
kits with sashes, hoops, pinstripes and trim that three colours and a pattern
enum cannot express, and the result read as a crest rather than a shirt.
The game already publishes the artwork, so use it.

Cached to disk rather than hotlinked, so a page view does not hit their CDN and
the site keeps working if it is unreachable. Files are named by short code, so
the page needs nothing but the club it already knows.
"""
import json
import os
import urllib.request

DIR = 'shirts'
SRC = 'https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_{code}{gk}-110.png'
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}


def path_for(short, gk=False):
    return os.path.join(DIR, f"{short}{'_gk' if gk else ''}.png")


def sync(teams, force=False):
    """Fetch any missing kit. `teams` is the bootstrap teams list.

    Returns (fetched, present, failed). Kits change once a season, so a file
    that exists is left alone.
    """
    os.makedirs(DIR, exist_ok=True)
    fetched = present = 0
    failed = []
    for t in teams:
        for gk in (False, True):
            dest = path_for(t['short_name'], gk)
            if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
                present += 1
                continue
            url = SRC.format(code=t['code'], gk='_1' if gk else '')
            try:
                req = urllib.request.Request(url, headers=UA)
                data = urllib.request.urlopen(req, timeout=25).read()
                if not data.startswith(b'\x89PNG'):
                    raise ValueError('not a png')
                with open(dest, 'wb') as f:
                    f.write(data)
                fetched += 1
            except Exception as exc:  # noqa: BLE001 - a missing kit is cosmetic
                failed.append(f"{t['short_name']}{'_gk' if gk else ''}: {exc}")
    return fetched, present, failed


def have():
    """Short codes we hold a kit for, so the page can fall back where we don't."""
    if not os.path.isdir(DIR):
        return set()
    return {f[:-4].replace('_gk', '') for f in os.listdir(DIR) if f.endswith('.png')}


if __name__ == '__main__':
    boot = json.load(open('bootstrap.json', encoding='utf-8'))
    got, had, bad = sync(boot['teams'])
    print(f'shirts: {got} fetched, {had} already cached')
    for b in bad:
        print('  failed:', b)
