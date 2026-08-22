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

# The shirt is drawn as the TOP HALF of a jersey - cropped at the chest, wider
# than it is tall - so it can fill the card's width without towering over the
# numbers below it. 52x26 units, scaled by CSS rather than a fixed pixel size.
# Traced from a photograph of a real tee rather than drawn from description,
# after five attempts from words all failed in different ways. Two things every
# one of those got wrong:
#   - the hem is ~60% of the armhole length, not ~32%, which is what made the
#     sleeves read as cones
#   - the hem's INNER end is the lowest point of the sleeve; the armpit sits
#     slightly above it and inboard, so the underarm seam runs up-and-in
# Proportions are the photograph's, so the box is 54x39 rather than 52x26 - a
# real tee cropped at the chest is not twice as wide as it is tall.
# Dialled in directly with the interactive editor rather than described in
# words - five attempts from descriptions all failed differently, and handing
# over sliders settled it in one pass.
# Dialled in with the interactive editor rather than described in words. Five
# attempts from written descriptions each failed differently; handing over
# sliders settled it in two passes. These are the editor's exact numbers.
# Dialled in with the interactive editor rather than described in words. Five
# attempts from written descriptions each failed differently; sliders settled it.
VIEWBOX = '-1 0 54 37'
BODY = ('M11.5 4 L20.5 2.1 Q26 6.5 31.5 2.1 L40.5 4 '
        'L52 15 L44 24 L41.5 22 L41.5 37 '
        'L10.5 37 L10.5 22 L8 24 L0 15 Z')
SLEEVE_L = 'M11.5 4 L0 15 L8 24 L10.5 22 Z'
SLEEVE_R = 'M40.5 4 L52 15 L44 24 L41.5 22 Z'
NECK = 'M20.5 2.1 Q26 6.5 31.5 2.1'
CODE_SIZE = 12.0
CODE_BASELINE = 27.70
# Full chest width, x10.5 to x41.5 between the armpits. The editor derives this
# from an ESTIMATED 1.86 units of text per size unit, which came out at 27.42 -
# but measured in the DOM the codes run 26.4 to 29.1 wide at size 12, so that
# estimate clipped BHA. Spanning the chest is correct for every club and reads
# as a sponsor band rather than a tag.
PLATE = {'x': 10.5, 'y': 16.54, 'width': 31.0, 'height': 14.94, 'rx': 3}


def geometry():
    """Everything a renderer needs to draw the shirt, for embedding in a page."""
    return {'viewBox': VIEWBOX, 'body': BODY, 'sleeveL': SLEEVE_L,
            'sleeveR': SLEEVE_R, 'neck': NECK, 'plate': PLATE,
            'codeSize': CODE_SIZE, 'codeBaseline': CODE_BASELINE}
