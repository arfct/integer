"""Build Integer Sans: a variable pixel font in which every instance is a real bitmap.

    python scripts/build.py [--out build] [--max-size 48]

Sources are glyphs/<grid>/<weight>.txt: one drawing per pixel grid (rows per
em) and weight. The build turns every horizontal run of ink into a rectangle
and packs all drawings into one variable font with two stepped axes:

  opsz  Size, 8 to --max-size. Each exact size (a grid times a whole number)
        is a master; avar maps are so steep that a font-size snaps to the
        nearest exact size at or below it, so `font-optical-sizing: auto`
        picks the right drawing by itself. Sizes that are a multiple of a
        grid reuse that grid's drawing (a duplicate master: more bytes, no
        more drawing).
  wght  400 Regular, 700 Bold; snaps at 550.

Drawings on different grids have different rectangle counts, so every glyph
is padded to the largest count with zero-size rectangles; the padding is
never rendered because no interpolation ever is. Metrics vary per master
through MVAR so the baseline lands on a whole pixel at every exact size.
"""
import argparse
import json
import os
import re

from fontTools import varLib
from fontTools.varLib import models
from fontTools.designspaceLib import (AxisDescriptor, DesignSpaceDocument,
                                      InstanceDescriptor, SourceDescriptor)
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable

FAMILY = 'Integer Sans'
VERSION = '0.2'
UPM = 5040                      # divisible by 8, 9, 10, 12, 14, 16; 11 rounds by 0.04%
WEIGHTS = [('light', 'Light', 200, 0), ('regular', 'Regular', 400, 1), ('bold', 'Bold', 800, 2)]
DEFAULT_WEIGHT = 1
HERE = os.path.dirname(os.path.abspath(__file__))
GLYPHS = os.path.join(HERE, '..', 'glyphs')

args = argparse.ArgumentParser()
args.add_argument('--out', default=os.path.join(HERE, '..', 'build'))
args.add_argument('--max-size', type=int, default=48)
args.add_argument('--min-size', type=int, default=8)
opt = args.parse_args()
os.makedirs(opt.out, exist_ok=True)


def parse(path):
    """A source file: header comments (# key: value) and glyph entries. Returns (meta, glyphs)."""
    text = open(path).read()
    meta = dict(re.findall(r'^# (\w+): (\S+)', text, flags=re.M))
    text = re.sub(r'^# .*\n?|^#\n', '', text, flags=re.M)
    glyphs = {}
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = [l for l in block.split('\n') if l]
        if lines[0].startswith('name:'):
            f = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
            cur = glyphs[f['name']] = {'unicode': [int(u[2:], 16) for u in f.get('unicode', '').split()],
                                       'advance': int(f['advance']), 'left': int(f.get('left', 0)), 'rows': []}
        else:
            cur['rows'] = lines
    return meta, glyphs


def load(path):
    """A generated source plus its hand overrides, as (ascent, descent, cap, xheight, glyphs)."""
    meta, glyphs = parse(path)
    override = path[:-4] + '.overrides.txt'
    if os.path.exists(override):
        _, extra = parse(override)
        glyphs.update(extra)
    grid = int(meta['grid'])
    ascent = int(meta['ascent'])
    descent = int(meta.get('descent', grid - ascent))
    return ascent, descent, int(meta.get('cap', 0)), int(meta.get('xheight', 0)), glyphs


def runs(rows, ascent):
    """[(x, y, length)] per horizontal run; y is the row's bottom edge, baseline 0."""
    out = []
    for i, line in enumerate(rows):
        y, x = ascent - 1 - i, 0
        while x < len(line):
            if line[x] == '#':
                x0 = x
                while x < len(line) and line[x] == '#':
                    x += 1
                out.append((x0, y, x - x0))
            else:
                x += 1
    return out


# Load every grid.
grids = {}
for d in sorted(os.listdir(GLYPHS), key=lambda s: int(s) if s.isdigit() else 0):
    if not d.isdigit():
        continue
    grids[int(d)] = {}
    for key, *_ in WEIGHTS:
        grids[int(d)][key] = load(os.path.join(GLYPHS, d, key + '.txt'))
names = [n for n in grids[16]['regular'][4] if n != '.notdef']
cmap = {cp: n for n in names for cp in grids[16]['regular'][4][n]['unicode']}

# Which sizes are exact, and which grid serves each (the finest one).
served = {}
for size in range(opt.min_size, opt.max_size + 1):
    for grid in sorted(grids, reverse=True):
        if size % grid == 0:
            served[size] = grid
            break
sizes = sorted(served)
assert 16 in served, 'the 16-row grid is the default'

# Rectangle count per glyph across every grid, for padding.
count = {n: max(len(runs(m[4][n]['rows'], m[0])) for grid in grids for m in grids[grid].values()) for n in names}


def build_master(size, weight_key, style, path):
    grid = served[size]
    ascent, descent_rows, cap, xh, glyphs = grids[grid][weight_key]
    px = UPM / grid
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(['.notdef'] + names)
    fb.setupCharacterMap(cmap)
    glyf, metrics = {}, {}
    for n in names:
        g = glyphs[n]
        pen = TTGlyphPen(None)
        rs = [(x + g['left'], y, w) for (x, y, w) in runs(g['rows'], ascent)]
        for (x, y, w) in rs + [(0, 0, 0)] * (count[n] - len(rs)):
            x0, x1, y0, y1 = round(x * px), round((x + w) * px), round(y * px), round((y + 1) * px)
            pen.moveTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.lineTo((x0, y0))
            pen.closePath()
        tt = pen.glyph()
        if tt.numberOfContours > 1:
            tt.flags[0] |= 0x40                       # OVERLAP_SIMPLE
        glyf[n] = tt
        lsb = min((c[0] for c in tt.coordinates), default=0) if rs else 0
        metrics[n] = (round(g['advance'] * px), lsb)
    pen = TTGlyphPen(None)
    pen.moveTo((round(px), 0)); pen.lineTo((round(6 * px), 0)); pen.lineTo((round(6 * px), round(7 * px)))
    pen.lineTo((round(px), round(7 * px))); pen.closePath()
    glyf['.notdef'] = pen.glyph()
    metrics['.notdef'] = (round(7 * px), round(px))
    asc, desc = round(ascent * px), round(descent_rows * px)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=asc, descent=-desc, lineGap=0)
    fb.setupNameTable({
        'familyName': FAMILY, 'styleName': style,
        'uniqueFontIdentifier': f'{FAMILY} {style} {VERSION}', 'fullName': f'{FAMILY} {style}',
        'psName': f'{FAMILY.replace(" ", "")}-{style.replace(" ", "")}', 'version': f'Version {VERSION}',
        'copyright': 'Copyright 2026 Artifact. Derived from Inter, Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter).',
        'licenseDescription': 'This Font Software is licensed under the SIL Open Font License, Version 1.1. '
                              'This license is available with a FAQ at: https://openfontlicense.org',
        'licenseInfoURL': 'https://openfontlicense.org',
        'manufacturer': 'Artifact', 'designer': 'Artifact',
    })
    wclass = next(w for k, _, w, _ in WEIGHTS if k == weight_key)
    fb.setupOS2(version=4, sTypoAscender=asc, sTypoDescender=-desc, sTypoLineGap=0,
                usWinAscent=asc, usWinDescent=desc, sxHeight=round(xh * px), sCapHeight=round(cap * px),
                fsSelection=0x80 | (0x20 if weight_key == 'bold' else 0x40 if weight_key == 'regular' else 0), fsType=0,
                usWeightClass=wclass, achVendID='ARFT')
    fb.setupPost()
    fb.save(path)


ds = DesignSpaceDocument()
size_map = []
for i, s in enumerate(sizes):
    size_map.append((s, i))
    if i + 1 < len(sizes):
        size_map.append((sizes[i + 1] - 0.01, i))
ds.addAxis(AxisDescriptor(tag='opsz', name='Size', minimum=sizes[0], default=16, maximum=sizes[-1],
                          map=size_map))
ds.addAxis(AxisDescriptor(tag='wght', name='Weight', minimum=200, default=400, maximum=800,
                          map=[(200, 0), (299.99, 0), (300, 1), (400, 1), (599.99, 1), (600, 2), (800, 2)]))
for s in sizes:
    for key, style, _, w in WEIGHTS:
        path = os.path.join(opt.out, 'masters', f'{s}-{key}.ttf')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        build_master(s, key, style, path)
        ds.addSource(SourceDescriptor(path=path, name=f'{s} {style}',
                                      location={'Size': sizes.index(s), 'Weight': w},
                                      familyName=FAMILY, styleName=style))
for key, style, _, w in WEIGHTS:
    ds.addInstance(InstanceDescriptor(familyName=FAMILY, styleName=style,
                                      location={'Size': sizes.index(16), 'Weight': w}))



def _exact_supports(self):
    """Give every master a tent bounded by its neighbours on each axis.

    fontTools extends a master's tent to the end of the axis and makes later
    masters compensate, which is exact in real arithmetic but leaves the
    renderer summing a dozen fixed-point scalars at every exact size. With
    neighbour-bounded tents, at a master location every scalar is exactly 0
    or 1, so each size renders its own drawing to the unit."""
    values = {}
    for loc in self.locations:
        for axis, v in loc.items():
            values.setdefault(axis, {0.0}).add(v)
    values = {a: sorted(vs) for a, vs in values.items()}
    supports = []
    for loc in self.locations:
        support = {}
        for axis, v in loc.items():
            if v == 0:
                continue
            vs = values[axis]
            i = vs.index(v)
            lower = vs[i - 1] if i > 0 else -1.0
            upper = vs[i + 1] if i + 1 < len(vs) else 1.0
            support[axis] = (max(lower, 0.0), v, upper) if v > 0 else (lower, v, min(upper, 0.0))
        supports.append(support)
    self.supports = supports
    self._computeDeltaWeights()


models.VariationModel._computeMasterSupports = _exact_supports
vf, _, _ = varLib.build(ds)
buildStatTable(vf, [
    {'tag': 'opsz', 'name': 'Size', 'values': [
        {'value': s, 'name': f'{s}', **({'flags': 0x2} if s == 16 else {})} for s in sizes]},
    {'tag': 'wght', 'name': 'Weight', 'values': [
        {'value': 200, 'name': 'Light'},
        {'value': 400, 'name': 'Regular', 'flags': 0x2, 'linkedValue': 800},
        {'value': 800, 'name': 'Bold'}]},
])
gasp = newTable('gasp')                     # Windows GDI: no grayscale, just the bitmap
gasp.version = 1
gasp.gaspRange = {0xFFFF: 0x0001}
vf['gasp'] = gasp
vf['head'].flags |= 0x0008                  # integer ppem
base = os.path.join(opt.out, f'{FAMILY.replace(" ", "")}-VF')
vf.save(base + '.ttf')
vf.flavor = 'woff2'
vf.save(base + '.woff2')
with open(os.path.join(opt.out, 'charset.txt'), 'w') as fh:        # for the specimen page
    fh.write(''.join(chr(cp) for cp in sorted(cmap) if cp >= 0x20))
with open(os.path.join(opt.out, 'sizes.json'), 'w') as fh:
    json.dump({'exact': {s: served[s] for s in sizes}, 'grids': sorted(grids),
               'weights': {w: key for key, _, w, _ in WEIGHTS},
               'H': {f'{s}/{w}': grids[served[s]][key][4]['H']['advance'] * s / served[s]
                     for s in sizes for key, _, w, _ in WEIGHTS}}, fh)
print(f'{len(names)} glyphs, grids {sorted(grids)}, {len(sizes)} exact sizes x {len(WEIGHTS)} weights '
      f'= {len(sizes) * len(WEIGHTS)} masters; ttf {os.path.getsize(base + ".ttf") / 1e6:.2f} MB, '
      f'woff2 {os.path.getsize(base + ".woff2") / 1e3:.0f} KB')
print('exact sizes:', ', '.join(f'{s} ({served[s]}×{s // served[s]})' for s in sizes))
