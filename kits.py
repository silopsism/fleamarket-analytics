"""Home-kit colours per club, for drawing a squad on a pitch.

Nothing in the FPL API carries kit colours, and pulling the official shirt images
would make every page depend on their CDN. So this is a hand-written table:
body colour, a second colour for stripes or sleeves, and the ink that stays
readable on top. `pattern` is how the two combine - plain, vertical stripes, or
halves - which is enough to tell twenty clubs apart at thumbnail size.

Promoted or unknown clubs fall back to a neutral kit rather than vanishing.
"""

# short: (body, trim, ink, pattern)
KITS = {
    'ARS': ('#e2231a', '#ffffff', '#ffffff', 'sleeve'),
    'AVL': ('#670e36', '#95bfe5', '#ffffff', 'sleeve'),
    'BHA': ('#0057b8', '#ffffff', '#ffffff', 'stripe'),
    'BOU': ('#da291c', '#000000', '#ffffff', 'stripe'),
    'BRE': ('#e30613', '#ffffff', '#ffffff', 'stripe'),
    'CHE': ('#034694', '#ffffff', '#ffffff', 'plain'),
    'COV': ('#78d0f3', '#000000', '#0b2434', 'plain'),
    'CRY': ('#1b458f', '#c4122e', '#ffffff', 'stripe'),
    'EVE': ('#003399', '#ffffff', '#ffffff', 'plain'),
    'FUL': ('#ffffff', '#000000', '#111111', 'sleeve'),
    'HUL': ('#f5a12d', '#000000', '#1a1200', 'stripe'),
    'IPS': ('#3a64a3', '#ffffff', '#ffffff', 'plain'),
    'LEE': ('#ffffff', '#1d428a', '#111111', 'plain'),
    'LIV': ('#c8102e', '#00b2a9', '#ffffff', 'plain'),
    'MCI': ('#6cabdd', '#1c2c5b', '#0b1b3a', 'plain'),
    'MUN': ('#da291c', '#fbe122', '#ffffff', 'plain'),
    'NEW': ('#241f20', '#ffffff', '#ffffff', 'stripe'),
    'NFO': ('#dd0000', '#ffffff', '#ffffff', 'plain'),
    'SUN': ('#eb172b', '#ffffff', '#ffffff', 'stripe'),
    'TOT': ('#ffffff', '#132257', '#111111', 'plain'),
    # recent top-flight clubs, so a mid-season promotion or a spy squad from an
    # older gameweek still draws correctly
    'BUR': ('#6c1d45', '#99d6ea', '#ffffff', 'sleeve'),
    'LEI': ('#003090', '#fdbe11', '#ffffff', 'plain'),
    'LUT': ('#f78f1e', '#002d5b', '#1a1200', 'plain'),
    'NOR': ('#fff200', '#00a650', '#1a1a00', 'plain'),
    'SHU': ('#ee2737', '#000000', '#ffffff', 'stripe'),
    'SOU': ('#d71920', '#ffffff', '#ffffff', 'stripe'),
    'WHU': ('#7a263a', '#1bb1e7', '#ffffff', 'sleeve'),
    'WOL': ('#fdb913', '#231f20', '#1a1200', 'plain'),
}
FALLBACK = ('#8a938c', '#ffffff', '#ffffff', 'plain')


def kit(short):
    return KITS.get(short, FALLBACK)


def as_dict():
    """{short: [body, trim, ink, pattern]} for embedding in a page."""
    out = {k: list(v) for k, v in KITS.items()}
    out['_'] = list(FALLBACK)
    return out
