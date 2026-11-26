"""Render Inter to pixel grids: the drawings for Integer Sans.

    python scripts/import-inter.py [--grids 8-24] [--weights light,regular,bold] [--charset charset.txt]

For each grid (rows per em) the importer fixes the vertical metrics once, in
whole rows, from Inter's proportions: descender, baseline, x-height, cap
height, and ascender. For each weight it picks the Inter weight whose vertical
stem is exactly the target number of pixels, instances Inter there, warps
every glyph's y coordinates with a piecewise-linear map so the metric lines
land on those rows (overshoots flattened onto them), and renders each
character with FreeType's autohinter in monochrome mode, which then only has
to snap stems and side bearings horizontally. The result is written to
glyphs/<grid>/<weight>.txt; glyphs/<grid>/<weight>.overrides.txt (hand edits)
is left alone and wins at build time.

Stem targets by weight, in pixels, from Inter's own stem-to-em ratios:
  light   max(1, round(ratio(300) * grid))
  regular max(1, round(ratio(400) * grid))
  bold    max(regular + 1, round(ratio(700) * grid))
When Inter cannot get heavy enough (small grids), the glyph is rendered at
Inter Black and smeared right by the missing pixels, the classic bitmap bold.

Each instance (one grid in one weight) has one stroke table, and every glyph
is drawn from it:
  stem      the target above, the width of a vertical stroke
  bar       the height of a horizontal stroke. Inter draws bars thinner than
            stems, so the bar is Inter's own, as the hinter rounds the H's,
            in Light and Regular. In Bold it is the stem wherever the
            x-height holds three bars and the two counters between them
            (e, a, s), each counter at least a row and at least the bar less
            one: x-height >= 3 * stem + 2 * max(1, stem - 1). Where it does
            not, the bar stays Inter's own: a bar raised part of the way is
            rounded up in one letter and down in the next. The outlines of
            an instance whose bar differs from Inter's are made heavier
            vertically until the H's bar is that many rows.
  diagonal  the row thickness that makes a leaning stroke as thick across as
            the stem: stem * sqrt(1 + lean^2), in whole pixels (diagonals.py)
  round     a round stroke is the stem at its sides and the bar at its top
            and bottom; the erosion takes it down to those.

--parity avv|all lets A V v (or those and W w M) change width by a pixel so
an apex is exactly one stroke wide; it is off by default.
"""
import argparse
import collections
import ctypes
import io
import math
import os
import sys
import tempfile
import time
import unicodedata

import freetype
import numpy as np
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diagonals    # noqa: E402

INTER = os.path.join(HERE, '..', 'vendor', 'inter', 'InterVariable.ttf')
UPM = 2048

args = argparse.ArgumentParser()
args.add_argument('--grids', default='7-48')
args.add_argument('--weights', default='light,regular,bold')
args.add_argument('--charset', default=os.path.join(HERE, '..', 'charset.txt'))
args.add_argument('--out', default=os.path.join(HERE, '..', 'glyphs'))
args.add_argument('--no-derive', action='store_true', help='skip the derivation stage (shared parts, accents)')
args.add_argument('--parity', default='off', choices=('off', 'avv', 'all'),
                  help='let A V v (avv) or A V v W w M (all) change width by a pixel for an apex one stroke wide')
args.add_argument('--no-redraw', action='store_true', help='skip the fixed-step redraw of the diagonal letters')
args.add_argument('--no-bars', action='store_true', help="leave the bars at the source's own thickness")
opt = args.parse_args()


def parse_range(s):
    out = []
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-')
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


grids = parse_range(opt.grids)
weights = opt.weights.split(',')
charset = sorted({int(l.strip()[2:], 16) for l in open(opt.charset) if l.strip().startswith('U+')})

# --- Inter, subset to the charset, as a variable font -----------------------
base = TTFont(INTER)
cmap = base.getBestCmap()
missing = [cp for cp in charset if cp not in cmap]
if missing:
    print('not in Inter:', ' '.join(f'U+{cp:04X}' for cp in missing))
charset = [cp for cp in charset if cp in cmap]
sub = subset.Subsetter(subset.Options(layout_features=[], name_IDs=['*'], notdef_outline=True,
                                      recalc_bounds=True, glyph_names=True))
sub.populate(unicodes=charset)
sub.subset(base)
buf = io.BytesIO()
base.save(buf)
VF = buf.getvalue()
names = {cp: base.getBestCmap()[cp] for cp in charset}


def instance(opsz, wght):
    f = TTFont(io.BytesIO(VF))
    return instantiateVariableFont(f, {'opsz': float(opsz), 'wght': float(wght)}, inplace=True,
                                   updateFontNames=False)


# --- Design-space measurements (unhinted) ----------------------------------
def top_of(font, name):
    g = font['glyf'][name]
    g.recalcBounds(font['glyf'])
    return g.yMax


def bottom_of(font, name):
    g = font['glyf'][name]
    g.recalcBounds(font['glyf'])
    return g.yMin


def stem_of(font):
    g = font['glyf']['I']
    g.recalcBounds(font['glyf'])
    return g.xMax - g.xMin


def measure(opsz):
    """Inter's metric lines at this optical size, in units: flat heights and overshoots."""
    ref = instance(opsz, 400)
    cap, xh = top_of(ref, 'H'), top_of(ref, 'x')
    return dict(cap=cap, x=xh, asc=top_of(ref, 'd'), desc=bottom_of(ref, 'p'),
                ovs_x=top_of(ref, 'o') - xh, ovs_c=top_of(ref, 'O') - cap, ovs_b=-bottom_of(ref, 'o'))


stems = {}
for w in range(100, 901, 20):
    stems[w] = stem_of(instance(28, w))
ratio = {k: stems[v] / UPM for k, v in (('light', 300), ('regular', 400), ('bold', 700))}
print('stem/em: light %.4f regular %.4f bold %.4f black %.4f' % (ratio['light'], ratio['regular'], ratio['bold'], stems[900] / UPM))


def weight_for_stem(units, opsz):
    """The Inter weight whose I stem is `units` wide, by bisection on the design axis."""
    if units >= stem_of(instance(opsz, 900)):
        return 900.0
    lo, hi = 100.0, 900.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if stem_of(instance(opsz, mid)) < units:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)


# --- Vertical fitting -------------------------------------------------------
def grid_metrics(grid, d):
    """Rows for each metric line at this grid, from Inter's proportions."""
    s = grid / UPM
    x = max(2, round(d['x'] * s))
    cap = max(x + 1, round(d['cap'] * s))
    asc = max(cap, round(d['asc'] * s))
    desc = max(1, round(-d['desc'] * s))
    ovs = 1 if d['ovs_x'] * s >= 0.5 else 0  # overshoot survives as a pixel only when it is big enough
    return dict(x=x, cap=cap, asc=asc, desc=desc, ovs=ovs)


def warp_map(grid, m, d):
    """(design y -> target y in units) control points, monotone, for this grid."""
    u = UPM / grid                          # units per pixel
    scale = m['cap'] * u / d['cap']         # the baseline-to-cap scale, continued above and below
    top = max(d['asc'], d['cap'] + d['ovs_c']) + 1
    bottom = d['desc'] - d['ovs_b'] - 1
    pts = [
        (bottom - 2000, -m['desc'] * u - 2000 * scale),
        (d['desc'] - d['ovs_b'], -(m['desc']) * u), (d['desc'], -m['desc'] * u),
        (-d['ovs_b'], 0.0), (0, 0.0),
        (d['x'], m['x'] * u), (d['x'] + d['ovs_x'], (m['x'] + m['ovs']) * u),
        (d['cap'], m['cap'] * u), (d['cap'] + d['ovs_c'], (m['cap'] + m['ovs']) * u),
        (d['asc'], m['asc'] * u),
        (top + 2000, max(m['asc'], m['cap'] + m['ovs']) * u + 2000 * scale),
    ]
    # Keep it monotone and strictly increasing in x.
    out = []
    for x, y in sorted(pts):
        if out and x <= out[-1][0]:
            continue
        if out and y < out[-1][1]:
            y = out[-1][1]
        out.append((x, y))
    return out


def warp_y(y, pts):
    if y <= pts[0][0]:
        (x0, y0), (x1, y1) = pts[0], pts[1]
    elif y >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
    else:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= y <= x1:
                break
    return y0 + (y - x0) * (y1 - y0) / (x1 - x0)


def warp_font(font, pts):
    glyf = font['glyf']
    # Decompose every composite before warping anything. Warped in place, a
    # composite whose component came earlier in glyph order was built from the
    # already warped component and warped again: the accented letters, i, j,
    # and the colon, which are composites in the source, landed a row off
    # their base letter at some grids.
    flat = {}
    for name in list(glyf.keys()):
        g = glyf[name]
        if g.isComposite():
            coords, ends, flags = g.getCoordinates(glyf)
            ng = Glyph()
            ng.numberOfContours = len(ends)
            ng.coordinates = GlyphCoordinates(coords)
            ng.endPtsOfContours = list(ends)
            ng.flags = bytearray(flags)
            ng.program = ttProgram.Program()
            flat[name] = ng
    for name, ng in flat.items():
        glyf[name] = ng
    for name in list(glyf.keys()):
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        g.coordinates = GlyphCoordinates([(x, round(warp_y(y, pts))) for x, y in g.coordinates])
        g.recalcBounds(glyf)
    font['head'].flags |= 0x0008


# --- Bars ---------------------------------------------------------------------
def bar_units(font):
    """Height of the H's crossbar in the outline, in units."""
    ys = sorted({y for _, y in font['glyf']['H'].coordinates})
    return ys[2] - ys[1] if len(ys) == 4 else None


def bar_rows(natural, stem, xheight, weight):
    """The instance's bar in rows; `natural` is the source's own as the hinter rounds it."""
    if weight == 'bold' and natural < stem and xheight >= 3 * stem + 2 * max(1, stem - 1):
        return stem
    return natural


def embolden_y(font, e):
    """Move every edge of every outline e/2 units up or down, outward for a
    positive e: horizontal strokes gain e in height and vertical ones keep
    their width. Each point moves by the y part of the mitred offset of its
    two edges."""
    glyf = font['glyf']
    for name in list(glyf.keys()):
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        pts = [tuple(p) for p in g.coordinates]
        out = list(pts)
        start = 0
        for end in g.endPtsOfContours:
            c = pts[start:end + 1]
            n = len(c)
            for i, p in enumerate(c):
                j = i - 1
                while c[j % n] == p and i - j < n:
                    j -= 1
                a = c[j % n]
                j = i + 1
                while c[j % n] == p and j - i < n:
                    j += 1
                b = c[j % n]
                lin, lout = math.hypot(p[0] - a[0], p[1] - a[1]), math.hypot(b[0] - p[0], b[1] - p[1])
                if not lin or not lout:
                    continue
                ix, iy, ox, oy = (p[0] - a[0]) / lin, (p[1] - a[1]) / lin, (b[0] - p[0]) / lout, (b[1] - p[1]) / lout
                d = ix * ox + iy * oy
                if d > -0.9375:
                    sy = max(-1.5, min(1.5, (ix + ox) / (1 + d)))
                    out[start + i] = (p[0], round(p[1] + e / 2 * sy))
            start = end + 1
        g.coordinates = GlyphCoordinates(out)
        g.recalcBounds(glyf)


def fit_bar(font, grid, m, rows):
    """Make the warped font's bars exactly `rows` pixels: thicken (or thin)
    the outlines vertically, then move the metric lines, which the thickening
    pushed out by half of it, back onto their rows."""
    u = UPM / grid
    have = bar_units(font)
    cap = m['cap'] * u
    if have is None or cap <= rows * u:
        return
    # Moving the lines back squeezes what lies between them by cap / (cap + e).
    e = cap * (rows * u - have) / (cap - rows * u)
    if abs(e) < 1:
        return
    embolden_y(font, e)
    top = max(m['asc'], m['cap'] + m['ovs']) * u
    pts = [(-m['desc'] * u - e / 2 - 2000, -m['desc'] * u - 2000), (-m['desc'] * u - e / 2, -m['desc'] * u), (-e / 2, 0.0)]
    pts += [(v * u + e / 2, v * u) for v in sorted({m['x'], m['x'] + m['ovs'], m['cap'], m['cap'] + m['ovs'], m['asc']})]
    pts.append((top + e / 2 + 2000, top + 2000))
    glyf = font['glyf']
    for name in list(glyf.keys()):
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        g.coordinates = GlyphCoordinates([(x, round(warp_y(y, pts))) for x, y in g.coordinates])
        g.recalcBounds(glyf)


# --- Rendering --------------------------------------------------------------
class _XHeightProp(ctypes.Structure):
    _fields_ = [('face', ctypes.c_void_p), ('limit', ctypes.c_uint)]


def bitmap_rows(bm):
    """A FreeType bitmap as rows: mono -> '#'/'.', gray -> 0..255."""
    if bm.pixel_mode == freetype.FT_PIXEL_MODE_MONO:
        return [''.join('#' if bm.buffer[r * bm.pitch + c // 8] & (0x80 >> (c % 8)) else '.'
                        for c in range(bm.width)) for r in range(bm.rows)]
    return [[bm.buffer[r * bm.pitch + c] for c in range(bm.width)] for r in range(bm.rows)]


def pieces(rows):
    """8-connected groups of ink, for rows of '#'/'.' or of booleans, by
    union-find over horizontal runs (fast enough for a 4x render)."""
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    prev = []
    for r in rows:
        cur, x, n = [], 0, len(r)
        while x < n:
            if r[x] is True or r[x] == '#':
                x0 = x
                while x < n and (r[x] is True or r[x] == '#'):
                    x += 1
                i = len(parent)
                parent.append(i)
                cur.append((x0, x - 1, i))
                for a, b, j in prev:              # touching, diagonals included
                    if a <= x and b >= x0 - 1:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[ri] = rj
            else:
                x += 1
        prev = cur
    return len({find(i) for i in range(len(parent))})


def thin(rows, cover, k=1, h=1, limit=0.95, orbit=None):
    """Pixel-perfect strokes k pixels wide vertically and h horizontally.

    Drops partially covered ink pixels, least covered first, while the stroke
    stays 8-connected, no stroke end is shortened, the pixel touches background
    orthogonally, and the pixel is surplus to the thickness: on a locally
    steep stroke its horizontal run is longer than k, on a shallow one its
    vertical run is longer than h. Snapped stems
    and bars sit at full coverage and are never candidates, so they define the
    thickness; curves and diagonals are eroded down to it. With an orbit (a
    mirrored glyph) pixels go in whole orbits, and an orbit stays when clearing
    it would split the glyph."""
    hgt, wid = len(rows), len(rows[0]) if rows else 0
    ink = [[c == '#' for c in r] for r in rows]

    def on(y, x):
        return 0 <= y < hgt and 0 <= x < wid and ink[y][x]

    def neighbours(y, x):
        return [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and on(y + dy, x + dx)]

    def run(y, x, dy, dx):
        n = 1
        for sgn in (1, -1):
            yy, xx = y + sgn * dy, x + sgn * dx
            while on(yy, xx):
                n += 1
                yy, xx = yy + sgn * dy, xx + sgn * dx
        return n

    def removable(y, x, group=((),)):
        ns = neighbours(y, x)
        if len(ns) < 2:
            return False                      # a stroke end
        if all(on(y + dy, x + dx) for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))):
            return False                      # interior: removal would open a hole
        rh, rv = run(y, x, 0, 1), run(y, x, 1, 0)
        steep = rv >= rh                      # locally vertical-ish: thickness is the horizontal run
        # Other pixels removed in the same symmetric group and lying in this run count too.
        same_row = sum(1 for py, px in group if py == y and px != x and abs(px - x) < rh)
        same_col = sum(1 for py, px in group if px == x and py != y and abs(py - y) < rv)
        if not (rh - same_row > k if steep else rv - same_col > h):
            return False                      # not surplus to the thickness
        groups = []
        for n in ns:
            joined = [gi for gi, grp in enumerate(groups) if any(abs(n[0] - m[0]) <= 1 and abs(n[1] - m[1]) <= 1 for m in grp)]
            if not joined:
                groups.append([n])
            else:
                merged = [n] + [m for gi in joined for m in groups[gi]]
                groups = [grp for gi, grp in enumerate(groups) if gi not in joined] + [merged]
        return len(groups) == 1

    def joined(y, x):
        """Clearing (y, x) keeps its ink neighbours one group: no piece splits off."""
        ns = neighbours(y, x)
        groups = []
        for n in ns:
            hit = [gi for gi, grp in enumerate(groups) if any(abs(n[0] - m[0]) <= 1 and abs(n[1] - m[1]) <= 1 for m in grp)]
            groups = [grp for gi, grp in enumerate(groups) if gi not in hit] + [[n] + [m for gi in hit for m in groups[gi]]]
        return len(groups) == 1

    changed = True
    while changed:
        changed = False
        cands = sorted(((cover[y][x], y, x) for y in range(hgt) for x in range(wid)
                        if ink[y][x] and cover[y][x] < limit), key=lambda t: t[0])
        for c, y, x in cands:
            if not ink[y][x]:
                continue
            o = orbit(y, x) if orbit else [(y, x)]
            if all(ink[py][px] and removable(py, px, o) for py, px in o):
                # A symmetric glyph loses whole orbits. Each pixel passed the
                # test alone; clear them one at a time and re-test the rest, so
                # an apex two pixels wide cannot go in one move and split the
                # glyph. The test is local (the 3x3 ring), so it costs nothing.
                done = []
                for py, px in o:
                    if done and not joined(py, px):
                        break
                    ink[py][px] = False
                    done.append((py, px))
                if len(done) < len(o):
                    for py, px in done:
                        ink[py][px] = True
                    continue
                changed = True
    return [''.join('#' if v else '.' for v in r) for r in ink]


def bitmap_rows_of_H(path, grid):
    face = freetype.Face(path)
    face.set_pixel_sizes(0, grid)
    face.load_char('H', freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_FORCE_AUTOHINT)
    face.glyph.render(freetype.FT_RENDER_MODE_MONO)
    return bitmap_rows(face.glyph.bitmap)


# Glyphs that Inter draws mirror-symmetric. Left-right mirrors about the ink's
# centre column; top-bottom about its centre row. Rotational symmetry (S, Z, N)
# is not enforced: those shapes differ top and bottom by design.
SYM_LR = set('A H I M O T U V W X Y i l o v w x 0 8 ! " * + - . : = ^ _ |'.split()) | {
    'Adieresis', 'Acircumflex', 'Aring', 'Odieresis', 'Ocircumflex', 'Udieresis', 'Ucircumflex', 'Idieresis', 'Icircumflex',
    'odieresis', 'ocircumflex', 'idieresis', 'icircumflex',
    'exclam', 'quotedbl', 'asterisk', 'plus', 'hyphen', 'period', 'colon', 'equal', 'asciicircum', 'underscore', 'bar',
    'exclamdown', 'dieresis', 'degree', 'periodcentered', 'brokenbar', 'multiply', 'bullet',
    'ellipsis', 'uni2423', 'zero', 'eight'}
# Not on the list although they look symmetric at a glance: a and u under a
# dieresis, circumflex or ring (the base letter is not symmetric, so mirroring
# folded it onto itself), and the tilde (point-symmetric, not mirror-symmetric).
SYM_TB = {'H', 'I', 'O', 'X', 'o', 'x', 'zero', 'hyphen', 'equal', 'plus', 'bar', 'brokenbar', 'parenleft', 'parenright',
          'bracketleft', 'bracketright', 'braceleft', 'braceright', 'less', 'greater', 'periodcentered', 'multiply', 'bullet',
          'colon', 'asterisk', 'degree', 'ordmasculine'} - {'asterisk', 'degree', 'ordmasculine'}


def full_width_bar(ink, y, x, my, x0, x1):
    """True when the horizontal run through (y, x), or through its mirror if
    (y, x) is clear, spans the whole ink width: a bar between two stems, as in
    H, which cannot be centred on an even cap. A curve's top never does."""
    row = ink[y] if ink[y][x] else ink[my]
    if not row[x]:
        return False
    a = b = x
    while a > 0 and row[a - 1]:
        a -= 1
    while b + 1 < len(row) and row[b + 1]:
        b += 1
    return a <= x0 and b >= x1


def tall_stem(ink, y, x, mx):
    """True when the ink pixel of the pair sits in a vertical run of 3+ rows
    whose mirror column is clear alongside it: a stem like T's on an odd
    width, not a crossing or an apex, which are short."""
    col = x if ink[y][x] else mx
    other = mx if ink[y][x] else x
    a = b = y
    while a > 0 and ink[a - 1][col]:
        a -= 1
    while b + 1 < len(ink) and ink[b + 1][col]:
        b += 1
    if b - a + 1 < 3:
        return False
    return sum(1 for r in range(a, b + 1) if ink[r][other]) <= (b - a + 1) // 3


def _mirror_pass(rows, cover, orig, lr, tb, union=False):
    """One axis of mirror symmetry about the ink bounding box; see symmetrize.
    With union, a disagreeing pair is always inked: the fallback when the
    plain pass would leave the glyph in more pieces."""
    ink = [[c == '#' for c in r] for r in rows]
    h, w = len(ink), len(ink[0]) if ink else 0
    ys = [y for y in range(h) if any(ink[y])]
    xs = [x for x in range(w) if any(ink[y][x] for y in range(h))]
    if not ys:
        return rows, cover
    x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
    cov = [list(r) for r in cover]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            my, mx = (y0 + y1 - y if tb else y), (x0 + x1 - x if lr else x)
            if (my, mx) <= (y, x):
                continue
            c = (cov[y][x] + cov[my][mx]) / 2
            cov[y][x] = cov[my][mx] = c
            if ink[y][x] == ink[my][mx]:
                continue
            solid = max(orig[y][x], orig[my][mx]) >= 0.9
            if tb and solid and full_width_bar(ink, y, x, my, x0, x1):
                continue                              # a bar facing an empty row: it cannot be centred on an even cap
            if lr and solid and tall_stem(ink, y, x, mx):
                continue                              # a stem facing an empty column: it cannot be centred on an odd width
            if union or c >= 0.6:
                state = True
            elif c <= 0.4:
                state = False
            elif solid:
                state = True                          # a crossing or apex on an even width: fill it out
            else:
                state = ink[y][x]                     # the left (or top) pixel wins, consistently
            ink[y][x] = ink[my][mx] = state
    return [''.join('#' if v else '.' for v in r) for r in ink], cov


def symmetrize(rows, cover, lr, tb, orig=None):
    """Make a bitmap mirror-symmetric about its ink bounding box.

    Left-right first, then top-bottom, each as a pass over mirrored pixel
    pairs. A disagreeing pair is set from its mean coverage: ink above 0.6,
    clear below 0.4; in between, a solid pixel (original coverage 0.9+) is a
    snapped feature: on the top-bottom axis a bar that cannot be centred on an
    even cap is left alone, on the left-right axis a crossing or apex on an
    even width is filled out; otherwise the left (or top) pixel's state wins
    so the choice is consistent along a staircase. Coverage is averaged over
    each pair too, so a thinning pass afterwards treats both sides alike.
    A pass that would change the number of pieces is redone as a union: a
    thin diagonal whose two legs the hinter snapped differently loses a row
    when both pixels of a low-coverage pair are cleared, and a one-pixel dot
    off the axis (a colon's, a dieresis's) vanishes. The union is kept when it
    keeps the count, or comes closer to it.
    Returns (rows, coverage, orbit) where orbit(y, x) lists a pixel's images
    under both flips, for thinning in symmetric groups."""
    orig = orig or cover

    def connected_pass(rows, cover, lr_, tb_):
        n = pieces(rows)
        out, cov = _mirror_pass(rows, cover, orig, lr_, tb_)
        if pieces(out) != n:
            u = _mirror_pass(rows, cover, orig, lr_, tb_, union=True)
            if abs(pieces(u[0]) - n) <= abs(pieces(out) - n):
                out, cov = u
        return out, cov

    if lr:
        # The solidity test must not see left and right differently, or the
        # top-bottom pass decides the two sides of a row inconsistently.
        ink0 = [[c == '#' for c in r] for r in rows]
        xs = [x for x in range(len(ink0[0]) if ink0 else 0) if any(row[x] for row in ink0)]
        if xs:
            x0, x1 = xs[0], xs[-1]
            orig = [[max(r[x], r[x0 + x1 - x]) if x0 <= x <= x1 else r[x] for x in range(len(r))] for r in orig]
        rows, cover = connected_pass(rows, cover, True, False)
    if tb:
        rows, cover = connected_pass(rows, cover, False, True)
    ink = [[c == '#' for c in r] for r in rows]
    h, w = len(ink), len(ink[0]) if ink else 0
    ys = [y for y in range(h) if any(ink[y])]
    xs = [x for x in range(w) if any(ink[y][x] for y in range(h))]
    if not ys:
        return rows, cover, (lambda y, x: [(y, x)])
    x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]

    def orbit(y, x):
        pts = {(y, x)}
        if lr:
            pts |= {(py, x0 + x1 - px) for py, px in pts}
        if tb:
            pts |= {(y0 + y1 - py, px) for py, px in pts}
        return sorted(pts)

    return rows, cover, orbit


def center_in_advance(rows, left, adv):
    """Equal side bearings for a symmetric glyph when the spare width is even."""
    if not rows:
        return left
    xs = [x for x in range(len(rows[0])) if any(r[x] == '#' for r in rows)]
    if not xs:
        return left
    width = xs[-1] - xs[0] + 1
    spare = adv - width
    if spare >= 0 and spare % 2 == 0:
        return spare // 2 - xs[0]
    return left


def bar_thickness(rows_H):
    """Rows of ink in the crossbar of a rendered H: the horizontal stem in pixels."""
    if not rows_H:
        return 1
    mid = len(rows_H[0]) // 2
    return max(1, sum(1 for r in rows_H if r[mid] == '#'))


def bridge(rows, cover, want, orbit=None):
    """Ink the best-covered clear pixel that touches two pieces (with its
    mirror orbit), until no more than `want` pieces remain or no single pixel
    joins two. For drawings the monochrome render or a pass left in more
    pieces than the outline has."""
    ink = [[c == '#' for c in r] for r in rows]
    h, w = len(ink), len(ink[0]) if ink else 0
    for _ in range(12):
        if pieces(ink) <= want:
            break
        lab, n = {}, 0
        todo = {(y, x) for y in range(h) for x in range(w) if ink[y][x]}
        while todo:
            n += 1
            stack = [todo.pop()]
            while stack:
                y, x = stack.pop()
                lab[(y, x)] = n
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        q = (y + dy, x + dx)
                        if q in todo:
                            todo.remove(q)
                            stack.append(q)
        best = None
        for y in range(h):
            for x in range(w):
                if ink[y][x] or cover[y][x] <= 0:
                    continue
                near = {lab[(y + dy, x + dx)] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (y + dy, x + dx) in lab}
                if len(near) >= 2 and (best is None or cover[y][x] > best[0]):
                    best = (cover[y][x], y, x)
        if best is None:
            break
        for py, px in (orbit(best[1], best[2]) if orbit else [(best[1], best[2])]):
            if 0 <= py < h and 0 <= px < w:
                ink[py][px] = True
    return [''.join('#' if v else '.' for v in r) for r in ink]


def outline_pieces(face, cp):
    """Pieces of the unhinted outline rendered at four times the grid: what the drawing should have."""
    face.load_char(cp, freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_NO_HINTING)
    face.glyph.render(freetype.FT_RENDER_MODE_MONO)
    bm = face.glyph.bitmap
    if not bm.rows:
        return 0
    buf = np.frombuffer(bytes(bm.buffer), dtype=np.uint8).reshape(bm.rows, bm.pitch)
    return pieces(np.unpackbits(buf, axis=1)[:, :bm.width].astype(bool).tolist())


def redraw_rows(name, rows, hint, stem, bar):
    """The fixed-step redraw (diagonals.py) of one rendered glyph: (rows, change in width, status)."""
    bm = np.array([[c == '#' for c in r] for r in rows], bool)
    hb = np.array([[c == '#' for c in r] for r in hint], bool) if hint and len(hint) == len(rows) and len(hint[0]) == len(rows[0]) else bm
    ys, xs = np.where(bm)
    if not len(ys):
        return rows, 0, 'same'
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    new, status = diagonals.redraw(name, bm[y0:y1, x0:x1], hb[y0:y1, x0:x1], stem, bar, opt.parity)
    if status != 'redrawn':
        return rows, 0, status
    grown = new.shape[1] - (x1 - x0)
    out = np.zeros((bm.shape[0], bm.shape[1] + grown), bool)
    out[y0:y1, x0:x0 + new.shape[1]] = new
    return [''.join('#' if v else '.' for v in r) for r in out], grown, status


def render_font(path, grid, smear, stem, tally=None):
    face = freetype.Face(path)
    prop = _XHeightProp(ctypes.cast(face._FT_Face, ctypes.c_void_p).value, 0)
    freetype.raw.FT_Property_Set(freetype.get_handle(), b'autofitter', b'increase-x-height', ctypes.byref(prop))
    face.set_pixel_sizes(0, grid)
    big = freetype.Face(path)
    big.set_pixel_sizes(0, grid * 4)
    flags = freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_FORCE_AUTOHINT
    face.load_char('H', flags)
    face.glyph.render(freetype.FT_RENDER_MODE_MONO)
    bar = bar_thickness(bitmap_rows(face.glyph.bitmap))
    out = {}
    for cp in charset:
        face.load_char(cp, flags)
        g = face.glyph
        g.render(freetype.FT_RENDER_MODE_MONO)
        rows, left, top = bitmap_rows(g.bitmap), g.bitmap_left, g.bitmap_top
        adv = (g.advance.x + 32) // 64
        if rows:
            face.load_char(cp, flags)
            g = face.glyph
            g.render(freetype.FT_RENDER_MODE_NORMAL)
            gray, gl, gt = bitmap_rows(g.bitmap), g.bitmap_left, g.bitmap_top
            cover = [[0.0] * len(rows[0]) for _ in rows]
            for y, r in enumerate(gray):
                for x, v in enumerate(r):
                    yy, xx = y + (top - gt), x + (gl - left)
                    if 0 <= yy < len(rows) and 0 <= xx < len(rows[0]):
                        cover[yy][xx] = v / 255.0
            name = names.get(cp, '')
            lr, tb = name in SYM_LR, name in SYM_TB
            orbit = None
            if lr or tb:
                orig = cover
                rows, cover, orbit = symmetrize(rows, cover, lr, tb, orig)
                rows = thin(rows, cover, k=stem, h=bar, orbit=orbit)
                rows, cover, orbit = symmetrize(rows, cover, lr, tb, orig)
                hint = rows
                rows = thin(rows, cover, k=stem, h=bar, orbit=orbit)
            else:
                hint = rows
                rows = thin(rows, cover, k=stem, h=bar)
            if pieces(rows) > 1:
                want = outline_pieces(big, cp)
                if pieces(rows) > want:
                    rows = bridge(rows, cover, want, orbit)
            if name in diagonals.RECIPES and not opt.no_redraw:
                rows, grown, status = redraw_rows(name, rows, hint, stem, bar)
                adv += grown
                if tally is not None:
                    tally[status] += 1
            if lr:
                left = center_in_advance(rows, left, adv)
        if smear and rows:
            rows = [''.join('#' if any(line[i - k] == '#' for k in range(0, smear + 1) if 0 <= i - k < len(line)) else '.'
                            for i in range(len(line) + smear)) for line in rows]
        out[cp] = (rows, left, top, adv + smear)
    return out


# --- Derived glyphs ---------------------------------------------------------
# Letters that share a part are drawn from one master instead of rendered
# alone, so b d p q share one bowl, n h u one arch, and an accented letter is
# its base letter's drawing with the accent set over it. Each rule runs after
# rendering, thinning, and mirroring; the derived drawing goes into
# <weight>.txt like any other, and <weight>.overrides.txt still wins at build
# time. The rules read the rendered masters, not their overrides: a hand fix
# to `b` does not reach `d`; override both, or switch the rule off here.
# The same goes for the dots: the source builds the colon from two periods and
# the semicolon from a period over the comma's drawing, so they are assembled
# from the rendered period and comma (see `punctuation`).
#
#   target  how        master  grids (None: every grid)
DERIVE = [
    ('d', 'mirror', 'b', None),      # b mirrored, at d's own left bearing
    ('p', 'bowl', 'b', None),        # b's x-height band flipped top to bottom, over p's own descender
    ('q', 'mirror', 'p', None),      # the derived p mirrored
    ('h', 'arch', 'n', None),        # n's x-height band under h's own ascender
    ('u', 'turn', 'n', None),        # n turned half a turn about the x-height band
]
ACCENTS = None                       # grids that compose accented letters from base + accent; None: every grid
# A rule is skipped for a grid and weight when the source itself draws the two
# letters differently: rendered unhinted at GUARD_PPEM, the master, transformed,
# must have the target's height to within half a grid pixel and differ from it
# by under GUARD grid pixels of mean outline offset (the pixels that differ
# over the outline's length). The source's b d p q and n h u differ by at most
# 0.11 px at grids 7 to 42 in every weight. At 43 to 48 the grid keeps the top
# overshoot row and flattens the bottom one, so b's bowl flipped is not p's
# (0.26 to 0.33 px) and n turned is one row taller than u: those are skipped.
GUARD, GUARD_PPEM = 0.2, 256
# An accent with no clear row over its letter goes up one row, and may leave
# the line box to do it: by at most ABOVE rows over the box's ascent. One row
# is all it ever takes. The accent is what lies above the letter's top row, so
# at worst its lowest row is the one on that row, and one row up it is clear;
# and the ascent is the tallest render, so an accent one row up is at most one
# row over it. A limit of two would never be used; none would let a later
# change to the rule push ink into the line above without anyone deciding to.
ABOVE = 1


def to_pixels(rows, left, top):
    """A drawing as a set of (y, x): y counts rows up from the baseline (0 is the row on it), x from the origin."""
    return {(top - 1 - i, left + j) for i, r in enumerate(rows) for j, c in enumerate(r) if c == '#'}


def from_pixels(px):
    if not px:
        return [], 0, 0
    ys, xs = [y for y, _ in px], [x for _, x in px]
    top, left = max(ys) + 1, min(xs)
    w, h = max(xs) - left + 1, top - min(ys)
    return [''.join('#' if (top - 1 - i, left + j) in px else '.' for j in range(w)) for i in range(h)], left, top


def x_span(px):
    xs = [x for _, x in px]
    return min(xs), max(xs)


def mirrored(px, at):
    """Mirror left-right, the ink's left edge at x = at."""
    a, b = x_span(px)
    return {(y, at + b - x) for y, x in px}


def shifted(px, at):
    a, _ = x_span(px)
    return {(y, x - a + at) for y, x in px}


def derive_glyph(how, src, dst, xh):
    """(pixels, advance) of dst re-drawn from src. src and dst are (pixels, advance).
    The target keeps its own left bearing; its advance moves only by the change
    in ink width, so a derived letter is never re-spaced."""
    (S, _), (D, dadv) = src, dst
    lsb, (d0, d1) = x_span(D)[0], x_span(D)
    if how == 'mirror':
        new = mirrored(S, lsb)
    elif how == 'turn':
        new = {(xh - 1 - y, x) for y, x in mirrored(S, lsb)}
    elif how == 'bowl':
        bowl = {(xh - 1 - y, x) for y, x in S if 0 <= y < xh}
        new = {(y, x) for y, x in D if not 0 <= y < xh} | shifted(bowl, lsb)
    elif how == 'arch':
        # h's stem runs on through the band: keep its own ink in the stem's
        # columns, or the overshoot row and n's notched shoulder cut it.
        stem = {x for y, x in D if y == xh}
        new = ({(y, x) for y, x in D if y >= xh or x in stem}
               | shifted({(y, x) for y, x in S if 0 <= y < xh}, lsb))
    else:
        raise ValueError(how)
    a, b = x_span(new)
    return new, dadv + (b - a) - (d1 - d0)


def accent_parts(ch):
    """(base char, is cedilla) for a Latin-1 letter that is a base plus one mark, or None."""
    nfd = unicodedata.normalize('NFD', ch)
    if len(nfd) != 2 or not nfd[0].isalpha() or nfd[0] == 'j':
        return None
    return nfd[0], nfd[1] == '\u0327'


def body(px, top_row, cedilla):
    """The pixels of a letter's body: below the base letter's top row, and above the baseline under a cedilla."""
    return {(y, x) for y, x in px if y < top_row and (y >= 0 or not cedilla)}


def touching(a, b):
    """True when a pixel of a has a pixel of b beside it, diagonals included."""
    return any((y + dy, x + dx) in b for y, x in a for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def crowds(accent, B):
    """True when there is no clear row between an accent and the letter under
    it: its lowest row is the one on the letter's top row, whether its ink
    touches the letter's or sits over a gap in it (the acute in the fork of Y)."""
    return touching(accent, B) or min(y for y, _ in accent) <= max(y for y, _ in B) + 1


def groups(px):
    """A set of pixels as its 8-connected pieces."""
    todo, out = set(px), []
    while todo:
        stack = [todo.pop()]
        piece = set(stack)
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (y + dy, x + dx)
                    if q in todo:
                        todo.remove(q)
                        piece.add(q)
                        stack.append(q)
        out.append(piece)
    return out


def compose(base, accented, top_row, cedilla, room, own=False):
    """base's drawing with the accent of `accented` over it, moved with the base's centre.
    With `own`, the other way round: the base's drawing is moved under the
    accent, and the letter keeps its own advance.

    The accent is what the accented render has above the base letter's top
    row. Where the hinter drew the body one row taller under an accent than
    alone (y and u at 44 rows and up), that row is body, not accent: a piece
    lying wholly in the first row and touching the body below is dropped when
    there is accent above it. An accent with no clear row between it and the
    base letter (`crowds`) goes up a row; one that has a clear row is not moved.
    `room` is the line box's ascent in rows, and the accent may end up to
    ABOVE rows over it: type may ink above its line box, and an accent run
    into its letter reads worse than one in the line gap."""
    (B, badv), (A, aadv) = base, accented
    keep = body(A, top_row, cedilla)
    accent = A - keep
    if not accent or not keep:
        return None
    if not cedilla:
        parts = groups(accent)
        stubs = [p for p in parts if all(y == top_row for y, _ in p) and touching(p, keep)]
        if stubs and len(stubs) < len(parts):
            accent = set().union(*(p for p in parts if p not in stubs))
    (a0, a1), (b0, b1) = x_span(keep), x_span(body(B, top_row, cedilla) or B)
    dx = int(round(((b0 + b1) - (a0 + a1)) / 2))
    if own:
        B, badv = {(y, x - dx) for y, x in B}, aadv
    else:
        accent = {(y, x + dx) for y, x in accent}
    if not cedilla and crowds(accent, B) and max(y for y, _ in accent) + 2 <= room + ABOVE:
        accent = {(y + 1, x) for y, x in accent}
    return B | accent, badv


SITS = ',\u201a\u201e'                 # marks that hang from the baseline row


def punctuation(px, outl, put):
    """The comma, colon and semicolon from their parts, as the source builds them.

    The comma and the low quotes are the right quote's drawing moved down, and
    its top is over half a pixel above the baseline at every grid; where the
    hinter set the whole mark below the baseline it is moved up to sit on it,
    unless it is a single row, which on the baseline would be a period.
    The colon is the period twice, the upper one topping out where the
    rendered colon does. The semicolon is the comma's drawing with the period
    over it at the colon's height, moved right by the difference of the two
    advances, as in the source."""
    def has(ch):
        return bool(px.get(ord(ch), ((), 0))[0])

    for ch in SITS:
        if has(ch) and outl.get(ch)[1] >= outl.px / 2:
            S, adv = px[ord(ch)]
            top = max(y for y, _ in S)
            if top < 0 and min(y for y, _ in S) < top:
                put(ord(ch), ({(y - top, x) for y, x in S}, adv))
    if not (has('.') and has(':')):
        return
    (D, dadv), (C, _) = px[ord('.')], px[ord(':')]
    up = max(y for y, _ in C) - max(y for y, _ in D)
    if up - 1 <= max(y for y, _ in D) - min(y for y, _ in D):
        return                                # no clear row between the two dots: keep the renders
    put(ord(':'), (D | {(y + up, x) for y, x in D}, dadv))
    if has(',') and has(';'):
        (L, ladv), (_, sadv) = px[ord(',')], px[ord(';')]
        dx = min(1, max(0, sadv - ladv))
        dot = {(y + up, x + dx) for y, x in D}
        if not touching(dot, L):
            put(ord(';'), (L | dot, ladv + dx))


class Outlines:
    """The warped source at GUARD_PPEM, unhinted, for the design guard."""

    def __init__(self, path, grid, ovs):
        self.face = freetype.Face(path)
        self.face.set_pixel_sizes(0, GUARD_PPEM)
        self.cache = {}
        self.px = GUARD_PPEM / grid                  # one grid pixel at this size
        self.band = self.get('x')[1] + round(ovs * self.px)

    def get(self, ch):
        if ch not in self.cache:
            self.face.load_char(ch, freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_NO_HINTING)
            self.face.glyph.render(freetype.FT_RENDER_MODE_MONO)
            bm = self.face.glyph.bitmap
            buf = np.frombuffer(bytes(bm.buffer), dtype=np.uint8).reshape(bm.rows, bm.pitch)
            self.cache[ch] = (np.unpackbits(buf, axis=1)[:, :bm.width].astype(bool), self.face.glyph.bitmap_top)
        return self.cache[ch]

    def rows(self, ch, lo=None, hi=None):
        """The outline's ink between rows lo and hi above the baseline, cropped."""
        a, top = self.get(ch)
        y = top - 1 - np.arange(a.shape[0])
        a = a[((y >= lo) if lo is not None else True) & ((y < hi) if hi is not None else True)] if (lo, hi) != (None, None) else a
        ys, xs = np.where(a)
        return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else a[:0, :0]

    def gap(self, a, b):
        """Mean offset between two outlines aligned at the ink's top left, in grid
        pixels: differing pixels over the outline's length (its edge pixels).
        Infinite when the heights differ by half a grid pixel or more."""
        if abs(a.shape[0] - b.shape[0]) >= self.px / 2:
            return float('inf')
        h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
        A, B = np.zeros((h, w), bool), np.zeros((h, w), bool)
        A[:a.shape[0], :a.shape[1]], B[:b.shape[0], :b.shape[1]] = a, b
        P = np.pad(A, 1)
        edge = A & ~(P[:-2, 1:-1] & P[2:, 1:-1] & P[1:-1, :-2] & P[1:-1, 2:])
        return float((A ^ B).sum()) / max(1, int(edge.sum())) / self.px

    def rule_gap(self, how, src, dst):
        xh = self.band
        if how == 'mirror':
            return self.gap(self.rows(src)[:, ::-1], self.rows(dst))
        if how == 'turn':
            return self.gap(self.rows(src)[::-1, ::-1], self.rows(dst))
        if how == 'bowl':
            return self.gap(self.rows(src, 0, xh)[::-1], self.rows(dst, 0, xh))
        if how == 'arch':
            return self.gap(self.rows(src, 0, xh), self.rows(dst, 0, xh))
        raise ValueError(how)

    def accent_gap(self, base, ch, top_row, cedilla):
        lo = 0 if cedilla else None
        return self.gap(self.rows(base, lo, top_row), self.rows(ch, lo, top_row))


def derive(rendered, path, grid, ovs, room):
    """Apply DERIVE, the punctuation and the accent rule to one grid and
    weight's drawings, in place. Returns (rules applied, rules skipped by the
    guard). The bowl and arch band runs from the baseline to the x-height plus
    the overshoot row, where a grid keeps one. `room` is the line box's ascent
    in rows: an accent moved clear of its letter ends at most ABOVE rows over it."""
    outl = Outlines(path, grid, ovs)
    px = {cp: (to_pixels(r, l, t), adv) for cp, (r, l, t, adv) in rendered.items()}
    xh = rendered[ord('x')][2] + ovs
    done, skipped = collections.Counter(), []

    def put(cp, new):
        rows, left, top = from_pixels(new[0])
        rendered[cp] = (rows, left, top, new[1])
        px[cp] = new

    for target, how, master, on in DERIVE:
        t, s = ord(target), ord(master)
        if (on is not None and grid not in on) or not (px.get(t, ({}, 0))[0] and px.get(s, ({}, 0))[0]):
            continue
        g = outl.rule_gap(how, master, target)
        if g > GUARD:
            skipped.append(f'{target}<{master} ' + ('height' if g == float('inf') else f'{g:.2f}px'))
            continue
        put(t, derive_glyph(how, px[s], px[t], xh))
        done[target] += 1
    punctuation(px, outl, put)
    dotted = {}                                             # dieresis letters composed below, and the base each stands on
    if ACCENTS is None or grid in ACCENTS:
        for cp in [c for c in rendered if 0xC0 <= c < 0x100]:
            parts = accent_parts(chr(cp))
            if not parts or ord(parts[0]) not in px or not px[cp][0]:
                continue
            base, cedilla = parts
            # An accent takes the place of i's dot: the base is i's stem, which
            # the source draws as the dotless i, and the accent is what lies
            # above that. These four keep their own advance and the stem goes
            # where they rendered it: the accents are wider than i, the hinter
            # gives them another advance than i's at about half the sizes, and
            # on i's advance they ran into f, l, b, k and d twice as often.
            shape = '\u0131' if base == 'i' else base
            if ord(shape) not in px or not px[ord(shape)][0]:
                continue
            top_row = rendered[ord(shape)][2]               # the accent is what lies above the base letter's top
            g = outl.accent_gap(shape, chr(cp), outl.get(shape)[1], cedilla)
            if g > GUARD:
                skipped.append(f'{chr(cp)}<{base} ' + ('height' if g == float('inf') else f'{g:.2f}px'))
                continue
            B, badv = px[ord(base)]
            if base == 'i':
                B = {(y, x) for y, x in B if y < top_row}
            new = compose((B, badv), px[cp], top_row, cedilla, room, own=base == 'i')
            if new:
                put(cp, new)
                done['accented'] += 1
                if base != 'i' and unicodedata.normalize('NFD', chr(cp))[1] == '\u0308':
                    dotted[cp] = B
    # A dieresis is two dots. Where one came out as a single piece (the mirror
    # pass filled the gap, or the render did) and another letter of the same
    # case has two at this size, it takes that pair, centred where its own
    # was: a pair with two like dots before a lopsided one, then the one
    # nearest its own in width. Over a letter that is its own mirror image the
    # pair is centred on the letter instead when its own mark was off it.
    pairs = {cp: px[cp][0] - B for cp, B in dotted.items()}
    for cp, B in dotted.items():
        if len(groups(pairs[cp])) != 1:
            continue
        a0, a1 = x_span(pairs[cp])
        donors = [(d != mirrored(d, x_span(d)[0]), abs((x_span(d)[1] - x_span(d)[0]) - (a1 - a0)), c)
                  for c, d in pairs.items() if chr(c).isupper() == chr(cp).isupper() and len(groups(d)) == 2]
        if not donors:
            continue
        d = pairs[min(donors)[2]]
        d0, d1 = x_span(d)
        dx = int(round(((a0 + a1) - (d0 + d1)) / 2))
        b0, b1 = x_span(B)
        if B == mirrored(B, b0):
            while (d0 + d1) / 2 + dx - (b0 + b1) / 2 > 0.5:
                dx -= 1
            while (b0 + b1) / 2 - (d0 + d1) / 2 - dx > 0.5:
                dx += 1
        new = {(y, x + dx) for y, x in d}
        low = min(y for y, _ in new) - (max(y for y, _ in B) + 1)
        new = {(y - max(0, low - 1), x) for y, x in new}    # no further off this letter than one clear row
        if crowds(new, B) and max(y for y, _ in new) + 2 <= room + ABOVE:
            new = {(y + 1, x) for y, x in new}
        if not touching(new, B):
            put(cp, (B | new, px[cp][1]))
            done['dieresis'] += 1
    return done, skipped


def write(path, grid, weight, note, m, ascent, descent, above, rendered):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(f'# Integer Sans, {grid}-row grid, {weight}. Generated from Inter 4.1 by scripts/import-inter.py\n'
                 f'# ({note}). Do not edit: put hand fixes in {weight}.overrides.txt.\n'
                 f'# grid: {grid}\n# ascent: {ascent}\n# descent: {descent}\n# above: {above}\n# cap: {m["cap"]}\n# xheight: {m["x"]}\n\n')
        for cp in charset:
            rows, left, top, adv = rendered[cp]
            # The box starts at the origin, or at the ink's left edge when that
            # lies left of it; `left` says where, and the build adds it back.
            off = min(left, 0)
            width = max(adv, left + (len(rows[0]) if rows else 0), 1) - off + 1
            # The box is the line box plus `above` rows over its ascent, for
            # the accents that rise out of it; the baseline is `descent` rows
            # from the bottom either way.
            box = [['.'] * width for _ in range(above + ascent + descent)]
            for i, r in enumerate(rows):
                y = above + ascent - top + i
                if 0 <= y < len(box):
                    for j, ch in enumerate(r):
                        x = left - off + j
                        if ch == '#' and 0 <= x < width:
                            box[y][x] = '#'
            written = sum(b.count('#') for b in box)
            assert written == sum(r.count('#') for r in rows), f'{names[cp]} at {grid} {weight}: ink lost in the box'
            extra = f'\nleft: {off}' if off < 0 else ''
            fh.write(f'name: {names[cp]}\nunicode: U+{cp:04X}\nadvance: {adv}{extra}\n\n'
                     + '\n'.join(''.join(b) for b in box) + '\n\n')


tmp = tempfile.mkdtemp()
started = time.time()
for grid in grids:
    opsz = min(32, max(14, grid))
    d = measure(opsz)
    m = grid_metrics(grid, d)
    pts = warp_map(grid, m, d)
    unit = UPM / grid
    s_reg = max(1, round(ratio['regular'] * grid))
    targets = {'light': max(1, round(ratio['light'] * grid)), 'regular': s_reg,
               'bold': max(s_reg + 1, round(ratio['bold'] * grid))}
    rendered, notes, derived, paths, redrawn = {}, {}, {}, {}, {}
    for weight in weights:
        px = targets[weight]
        wght = weight_for_stem(px * unit, opsz)
        smear = max(0, px - round(stem_of(instance(opsz, 900)) / unit)) if wght == 900.0 else 0
        font = instance(opsz, wght)
        warp_font(font, pts)
        path = os.path.join(tmp, f'inter-{grid}-{weight}.ttf')
        font.save(path)
        # The bar the hinter gives the source's own outline, then the
        # instance's. Only an instance whose bar differs from the source's
        # is refitted, a little over the whole row if the hinter rounds the
        # first try down: refitting moves every horizontal edge, and where
        # the source's bar already serves, its drawings are left alone.
        own = bar_thickness(bitmap_rows_of_H(path, grid))
        want = own if opt.no_bars else bar_rows(own, px - smear, m['x'], weight)
        for over in ((0, 0.2, 0.4, -0.2) if want != own else ()):
            font = instance(opsz, wght)
            warp_font(font, pts)
            fit_bar(font, grid, m, want + over)
            font.save(path)
            if bar_thickness(bitmap_rows_of_H(path, grid)) == want:
                break
        redrawn[weight] = collections.Counter()
        rendered[weight] = render_font(path, grid, smear, stem=px - smear, tally=redrawn[weight])
        paths[weight] = path
        notes[weight] = f'opsz {opsz}, wght {wght}, stem {px}px, bar {bar_thickness(bitmap_rows_of_H(path, grid))}px' + (f', smear {smear}' if smear else '')
    # One line box per grid, shared by every weight. The ascent is fixed by
    # the renders, before the derived stage, which may set an accent one row
    # over it (ABOVE) and changes nothing else about the box. The descent
    # is the metric row unless ink goes deeper.
    ascent = max([m['asc'] + 1] + [top for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    if not opt.no_derive:
        for weight in weights:
            done, skipped = derive(rendered[weight], paths[weight], grid, m['ovs'], ascent)
            derived[weight] = f'derived {sum(done.values())}' + (f', skipped {" ".join(skipped)}' if skipped else '')
    # The line box does not grow for an accent raised out of it; the drawings'
    # box does, by the same rows in every weight (`above` in the header).
    above = max([0] + [top - ascent for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    assert above <= ABOVE, f'{grid}: ink {above} rows over the line box'
    descent = max([m['desc']] + [len(rows) - top for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    for weight in weights:
        write(os.path.join(opt.out, str(grid), weight + '.txt'), grid, weight, notes[weight], m, ascent, descent, above, rendered[weight])
    print(f'grid {grid:2d}: x {m["x"]} cap {m["cap"]} asc {m["asc"]} desc {m["desc"]} ovs {m["ovs"]} | box {ascent}+{descent}, ink {above} above | '
          + ' | '.join(f'{w} {notes[w]}' + (f', {derived[w]}' if w in derived else '')
                       + f', redrawn {redrawn[w]["redrawn"]} kept {redrawn[w]["kept"]}' for w in weights), flush=True)
print(f'{len(grids)} grids in {time.time() - started:.0f} s')
