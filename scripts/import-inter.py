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
"""
import argparse
import ctypes
import io
import os
import tempfile

import freetype
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont

HERE = os.path.dirname(os.path.abspath(__file__))
INTER = os.path.join(HERE, '..', 'vendor', 'inter', 'InterVariable.ttf')
UPM = 2048

args = argparse.ArgumentParser()
args.add_argument('--grids', default='8-24')
args.add_argument('--weights', default='light,regular,bold')
args.add_argument('--charset', default=os.path.join(HERE, '..', 'charset.txt'))
args.add_argument('--out', default=os.path.join(HERE, '..', 'glyphs'))
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
            glyf[name] = g = ng
        if g.numberOfContours <= 0:
            continue
        g.coordinates = GlyphCoordinates([(x, round(warp_y(y, pts))) for x, y in g.coordinates])
        g.recalcBounds(glyf)
    font['head'].flags |= 0x0008


# --- Rendering --------------------------------------------------------------
class _XHeightProp(ctypes.Structure):
    _fields_ = [('face', ctypes.c_void_p), ('limit', ctypes.c_uint)]


def bitmap_rows(bm):
    """A FreeType bitmap as rows: mono -> '#'/'.', gray -> 0..255."""
    if bm.pixel_mode == freetype.FT_PIXEL_MODE_MONO:
        return [''.join('#' if bm.buffer[r * bm.pitch + c // 8] & (0x80 >> (c % 8)) else '.'
                        for c in range(bm.width)) for r in range(bm.rows)]
    return [[bm.buffer[r * bm.pitch + c] for c in range(bm.width)] for r in range(bm.rows)]


def thin(rows, cover, k=1, h=1, limit=0.95, orbit=None):
    """Pixel-perfect strokes k pixels wide vertically and h horizontally.

    Drops partially covered ink pixels, least covered first, while the stroke
    stays 8-connected, no stroke end is shortened, the pixel touches background
    orthogonally, and the pixel is surplus to the thickness: on a locally
    steep stroke its horizontal run is longer than k, on a shallow one its
    vertical run is longer than h. Snapped stems
    and bars sit at full coverage and are never candidates, so they define the
    thickness; curves and diagonals are eroded down to it."""
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
                for py, px in o:                      # a symmetric glyph loses whole orbits
                    ink[py][px] = False
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
SYM_LR = set('A H I M O T U V W X Y i l o v w x 0 8 ! " * + - . : = ^ _ | ~'.split()) | {
    'Adieresis', 'Acircumflex', 'Aring', 'Odieresis', 'Ocircumflex', 'Udieresis', 'Ucircumflex', 'Idieresis', 'Icircumflex',
    'adieresis', 'acircumflex', 'aring', 'odieresis', 'ocircumflex', 'udieresis', 'ucircumflex', 'idieresis', 'icircumflex',
    'exclam', 'quotedbl', 'asterisk', 'plus', 'hyphen', 'period', 'colon', 'equal', 'asciicircum', 'underscore', 'bar',
    'asciitilde', 'exclamdown', 'dieresis', 'degree', 'periodcentered', 'brokenbar', 'macron', 'multiply', 'bullet',
    'ellipsis', 'quotedblbase', 'quotedblleft', 'quotedblright', 'uni2423', 'zero', 'eight', 'AE', 'ae', 'logicalnot'} - {'AE', 'ae', 'logicalnot', 'quotedblbase', 'quotedblleft', 'quotedblright', 'macron'}
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


def _mirror_pass(rows, cover, orig, lr, tb):
    """One axis of mirror symmetry about the ink bounding box; see symmetrize."""
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
            if c >= 0.6:
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
    Returns (rows, coverage, orbit) where orbit(y, x) lists a pixel's images
    under both flips, for thinning in symmetric groups."""
    orig = orig or cover
    if lr:
        # The solidity test must not see left and right differently, or the
        # top-bottom pass decides the two sides of a row inconsistently.
        ink0 = [[c == '#' for c in r] for r in rows]
        xs = [x for x in range(len(ink0[0]) if ink0 else 0) if any(row[x] for row in ink0)]
        if xs:
            x0, x1 = xs[0], xs[-1]
            orig = [[max(r[x], r[x0 + x1 - x]) if x0 <= x <= x1 else r[x] for x in range(len(r))] for r in orig]
        rows, cover = _mirror_pass(rows, cover, orig, True, False)
    if tb:
        rows, cover = _mirror_pass(rows, cover, orig, False, True)
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


def render_font(path, grid, smear, stem):
    face = freetype.Face(path)
    prop = _XHeightProp(ctypes.cast(face._FT_Face, ctypes.c_void_p).value, 0)
    freetype.raw.FT_Property_Set(freetype.get_handle(), b'autofitter', b'increase-x-height', ctypes.byref(prop))
    face.set_pixel_sizes(0, grid)
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
            if lr or tb:
                orig = cover
                rows, cover, orbit = symmetrize(rows, cover, lr, tb, orig)
                rows = thin(rows, cover, k=stem, h=bar, orbit=orbit)
                rows, cover, orbit = symmetrize(rows, cover, lr, tb, orig)
                rows = thin(rows, cover, k=stem, h=bar, orbit=orbit)
            else:
                rows = thin(rows, cover, k=stem, h=bar)
            if lr:
                left = center_in_advance(rows, left, adv)
        if smear and rows:
            rows = [''.join('#' if any(line[i - k] == '#' for k in range(0, smear + 1) if 0 <= i - k < len(line)) else '.'
                            for i in range(len(line) + smear)) for line in rows]
        out[cp] = (rows, left, top, adv + smear)
    return out


def write(path, grid, weight, note, m, ascent, descent, rendered):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(f'# Integer Sans, {grid}-row grid, {weight}. Generated from Inter 4.1 by scripts/import-inter.py\n'
                 f'# ({note}). Do not edit: put hand fixes in {weight}.overrides.txt.\n'
                 f'# grid: {grid}\n# ascent: {ascent}\n# descent: {descent}\n# cap: {m["cap"]}\n# xheight: {m["x"]}\n\n')
        for cp in charset:
            rows, left, top, adv = rendered[cp]
            width = max(adv, left + (len(rows[0]) if rows else 0), 1) + 1
            box = [['.'] * width for _ in range(ascent + descent)]
            for i, r in enumerate(rows):
                y = ascent - top + i
                if 0 <= y < len(box):
                    for j, ch in enumerate(r):
                        x = left + j
                        if ch == '#' and 0 <= x < width:
                            box[y][x] = '#'
            extra = f'\nleft: {left}' if left < 0 else ''
            fh.write(f'name: {names[cp]}\nunicode: U+{cp:04X}\nadvance: {adv}{extra}\n\n'
                     + '\n'.join(''.join(b) for b in box) + '\n\n')


tmp = tempfile.mkdtemp()
for grid in grids:
    opsz = min(32, max(14, grid))
    d = measure(opsz)
    m = grid_metrics(grid, d)
    pts = warp_map(grid, m, d)
    unit = UPM / grid
    s_reg = max(1, round(ratio['regular'] * grid))
    targets = {'light': max(1, round(ratio['light'] * grid)), 'regular': s_reg,
               'bold': max(s_reg + 1, round(ratio['bold'] * grid))}
    rendered, notes = {}, {}
    for weight in weights:
        px = targets[weight]
        wght = weight_for_stem(px * unit, opsz)
        smear = max(0, px - round(stem_of(instance(opsz, 900)) / unit)) if wght == 900.0 else 0
        font = instance(opsz, wght)
        warp_font(font, pts)
        path = os.path.join(tmp, f'inter-{grid}-{weight}.ttf')
        font.save(path)
        rendered[weight] = render_font(path, grid, smear, stem=px - smear)
        notes[weight] = f'opsz {opsz}, wght {wght}, stem {px}px, bar {bar_thickness(bitmap_rows_of_H(path, grid))}px' + (f', smear {smear}' if smear else '')
    # One line box per grid, shared by every weight.
    ascent = max([m['asc'] + 1] + [top for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    descent = max([m['desc']] + [len(rows) - top for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    for weight in weights:
        write(os.path.join(opt.out, str(grid), weight + '.txt'), grid, weight, notes[weight], m, ascent, descent, rendered[weight])
    print(f'grid {grid:2d}: x {m["x"]} cap {m["cap"]} asc {m["asc"]} desc {m["desc"]} ovs {m["ovs"]} | box {ascent}+{descent} | '
          + ' | '.join(f'{w} {notes[w]}' for w in weights))
