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


def thin(rows, cover, limit=0.95):
    """Pixel-perfect 1px strokes: drop partially covered ink pixels that are not
    needed to keep the stroke connected (never ends, never full pixels).

    rows: list of str ('#'/'.'), cover: same shape, 0..1. Removal is in order of
    least coverage and repeats until stable. A pixel is removable when its ink
    neighbours stay 8-connected through the 3x3 neighbourhood without it."""
    h, w = len(rows), len(rows[0]) if rows else 0
    ink = [[c == '#' for c in r] for r in rows]

    def neighbours(y, x):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy or dx) and 0 <= y + dy < h and 0 <= x + dx < w and ink[y + dy][x + dx]:
                    out.append((dy, dx))
        return out

    def simple(y, x):
        """Removable: its ink neighbours stay one 8-connected group without it,
        it is not a stroke end, and it touches background orthogonally."""
        ns = neighbours(y, x)
        if len(ns) < 2:
            return False
        if all(0 <= y + dy < h and 0 <= x + dx < w and ink[y + dy][x + dx] for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))):
            return False                      # interior pixel: removal would open a hole
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
        cands = sorted(((cover[y][x], y, x) for y in range(h) for x in range(w)
                        if ink[y][x] and cover[y][x] < limit), key=lambda t: t[0])
        for c, y, x in cands:
            if ink[y][x] and simple(y, x):
                ink[y][x] = False
                changed = True
    return [''.join('#' if v else '.' for v in r) for r in ink]


def render_font(path, grid, smear, pixel_perfect):
    face = freetype.Face(path)
    prop = _XHeightProp(ctypes.cast(face._FT_Face, ctypes.c_void_p).value, 0)
    freetype.raw.FT_Property_Set(freetype.get_handle(), b'autofitter', b'increase-x-height', ctypes.byref(prop))
    face.set_pixel_sizes(0, grid)
    flags = freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_FORCE_AUTOHINT
    out = {}
    for cp in charset:
        face.load_char(cp, flags)
        g = face.glyph
        g.render(freetype.FT_RENDER_MODE_MONO)
        rows, left, top = bitmap_rows(g.bitmap), g.bitmap_left, g.bitmap_top
        adv = (g.advance.x + 32) // 64
        if pixel_perfect and rows:
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
            rows = thin(rows, cover)
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
        rendered[weight] = render_font(path, grid, smear, pixel_perfect=(px == 1))
        notes[weight] = f'opsz {opsz}, wght {wght}, stem {px}px' + (f', smear {smear}' if smear else '')
    # One line box per grid, shared by every weight.
    ascent = max([m['asc'] + 1] + [top for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    descent = max([m['desc']] + [len(rows) - top for r in rendered.values() for rows, _, top, _ in r.values() if rows])
    for weight in weights:
        write(os.path.join(opt.out, str(grid), weight + '.txt'), grid, weight, notes[weight], m, ascent, descent, rendered[weight])
    print(f'grid {grid:2d}: x {m["x"]} cap {m["cap"]} asc {m["asc"]} desc {m["desc"]} ovs {m["ovs"]} | box {ascent}+{descent} | '
          + ' | '.join(f'{w} {notes[w]}' for w in weights))
