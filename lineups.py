"""Who starts next week, from injuries and recent starts.

Two signals decide a lineup and nothing else comes close:

  * whether the player is fit
  * whether he has been starting LATELY

Recency is what separates a favoured starter from a rotation option without
having to model rotation at all. Three starts in a row is a nailed player; three
starts out of the last six, alternating, is a squad player - and a simple start
rate cannot tell those apart, while a recency-weighted one does it for free. It
also handles a returning injury without special-casing: the absences age out.

Actual starts come from event/{gw}/live, which reports every player's `starts`
flag for a gameweek in a single request. Finished gameweeks never change, so
they are cached and fetched once.
"""
import json
import os
import urllib.request

CACHE = 'starts_cache.json'
UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}
LIVE = 'https://fantasy.premierleague.com/api/event/{gw}/live/'

# How fast the past stops mattering. 0.72 puts roughly half the weight on the
# last two gameweeks, which is about how quickly a manager's preference reads.
DECAY = 0.72
# Below this many observed gameweeks the sample says little, and the caller
# should keep leaning on its season-long baseline instead.
MIN_WEEKS = 2


def _load():
    try:
        with open(CACHE, encoding='utf-8') as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception:          # noqa: BLE001 - a cold cache is normal
        return {}


def fetch(finished_gws, cache=None):
    """{gw: {player_id: [started, minutes]}} for every finished gameweek."""
    data = _load() if cache is None else cache
    fresh = False
    for gw in finished_gws:
        if gw in data:
            continue
        try:
            req = urllib.request.Request(LIVE.format(gw=gw), headers=UA)
            live = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as exc:  # noqa: BLE001 - a missing week degrades, not fails
            print(f'lineups: GW{gw} unavailable ({exc})')
            continue
        data[gw] = {str(e['id']): [int(e['stats'].get('starts') or 0),
                                   int(e['stats'].get('minutes') or 0)]
                    for e in live['elements']}
        fresh = True
    if fresh:
        try:
            with open(CACHE, 'w', encoding='utf-8') as f:
                json.dump({str(k): v for k, v in data.items()}, f)
        except Exception as exc:  # noqa: BLE001
            print('lineups: cache not written:', exc)
    return data


def start_probability(element, history, club_gws):
    """How likely this player is to start the next one, in 0..1.

    `history` is {gw: [started, minutes]} for this player, `club_gws` the
    gameweeks his club actually played - so a blank is absent from the sample
    rather than counted as a benching.
    """
    weeks = [g for g in sorted(club_gws) if g in history]
    if not weeks:
        return None, 0
    num = den = 0.0
    for i, gw in enumerate(reversed(weeks)):      # i = 0 is the most recent
        w = DECAY ** i
        num += w * (1 if history[gw][0] else 0)
        den += w
    p = num / den if den else 0.0

    # Fitness overrides form: a 75% doubt is a 75% starter at best, and anyone
    # flagged unavailable is not in the XI however nailed he was a week ago.
    status = element.get('status', 'a')
    chance = element.get('chance_of_playing_next_round')
    if status in ('i', 'u', 'n', 's') and (chance is None or chance == 0):
        return 0.0, len(weeks)
    if chance is not None and chance < 100:
        p *= chance / 100.0
    return p, len(weeks)


FORMATION = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}


def predicted_xi(players):
    """Best legal XI from [(element, probability)], most likely first."""
    ranked = sorted((p for p in players if p[1] is not None),
                    key=lambda p: -p[1])
    xi, per_pos = [], {1: 0, 2: 0, 3: 0, 4: 0}
    for el, prob in ranked:
        if len(xi) >= 11:
            break
        pos = el['element_type']
        lo, hi = FORMATION[pos]
        if per_pos[pos] >= hi:
            continue
        need = sum(max(FORMATION[k][0] - per_pos[k], 0) for k in FORMATION if k != pos)
        if 11 - len(xi) - 1 < need:
            continue
        xi.append((el, prob))
        per_pos[pos] += 1
    return xi
