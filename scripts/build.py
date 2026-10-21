"""Build a variable pixel font from the text bitmaps in glyphs/.

    python scripts/build.py [--family NAME] [--primitive pixels|runs] [--out build]

Every glyph is drawn on a 16-row grid (100 font units per pixel on a 1600-unit
em). The build turns ink into rectangles and makes them interpolate:

  wght  Weight. Each rectangle widens to the right by k pixels and the advance
        grows by k: 0 at Regular (400), 1 at Bold (700). This is the classic
        one-pixel "smear" bold, made continuous.
  slnt  Slant. Each row shifts right by floor(y / 3) pixels (about 18 degrees
        at the end of the axis); the baseline row stays put.
  ROND  Roundness (pixels primitive only). Corner radius of every pixel, from a
        square to a half-pixel radius, so a stem becomes a string of dots.

Primitives:
  pixels  one 12-point rounded rectangle per pixel; supports every axis.
  runs    one 4-point rectangle per horizontal run; smallest file, no ROND.
"""
import argparse
import os
import re

from fontTools import varLib
from fontTools.designspaceLib import (AxisDescriptor, DesignSpaceDocument,
                                      InstanceDescriptor, SourceDescriptor)
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen

PX = 100
UPM = 16 * PX
ASC, DESC = 13, 3          # rows above and below the baseline
CAP, XHEIGHT = 9, 7
VERSION = '0.1'

args = argparse.ArgumentParser()
args.add_argument('--family', default='Integer')
args.add_argument('--primitive', choices=['pixels', 'runs'], default='pixels')
args.add_argument('--out', default='build')
args.add_argument('--glyphs', default='glyphs')
opt = args.parse_args()
os.makedirs(opt.out, exist_ok=True)


def parse_sources(folder):
    """Read every glyphs/*.txt into [{name, unicode, advance, rows}]."""
    glyphs = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith('.txt'):
            continue
        text = open(os.path.join(folder, fn)).read()
        text = re.sub(r'^#.*\n?', '', text, flags=re.M)
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = [l for l in block.strip().split('\n') if l]
            if not lines:
                continue
            if lines[0].startswith('name:'):
                meta = dict(l.split(':', 1) for l in lines)
                meta = {k.strip(): v.strip() for k, v in meta.items()}
                glyphs.append({
                    'name': meta['name'],
                    'unicode': [int(u[2:], 16) for u in meta.get('unicode', '').split()],
                    'advance': int(meta['advance']),
                    'rows': [],
                })
            else:                      # a bitmap block follows its header
                glyphs[-1]['rows'] = lines
    return glyphs


def runs_of(rows):
    """[(x, y, length)] for each horizontal run; y is the row's bottom edge, baseline = 0."""
    out = []
    for i, line in enumerate(rows):
        y = ASC - 1 - i
        x = 0
        while x < len(line):
            if line[x] == '#':
                x0 = x
                while x < len(line) and line[x] == '#':
                    x += 1
                out.append((x0, y, x - x0))
            else:
                x += 1
    return out


def rounded_rect(pen, x0, y0, x1, y1, r):
    """Clockwise rounded rectangle with 12 points, so square and round masters match."""
    pen.moveTo((x0 + r, y1))
    pen.lineTo((x1 - r, y1)); pen.qCurveTo((x1, y1), (x1, y1 - r))
    pen.lineTo((x1, y0 + r)); pen.qCurveTo((x1, y0), (x1 - r, y0))
    pen.lineTo((x0 + r, y0)); pen.qCurveTo((x0, y0), (x0, y0 + r))
    pen.lineTo((x0, y1 - r)); pen.qCurveTo((x0, y1), (x0 + r, y1))
    pen.closePath()


def rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.lineTo((x0, y0))
    pen.closePath()


def slant_shift(y):
    """Horizontal pixel shift of the row whose bottom edge is y, at full slant."""
    return (y // 3) if y >= 0 else -((-y + 2) // 3)


def build_master(glyphs, *, smear, slant, radius, style, path):
    fb = FontBuilder(UPM, isTTF=True)
    order = ['.notdef'] + [g['name'] for g in glyphs if g['name'] != '.notdef']
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({cp: g['name'] for g in glyphs for cp in g['unicode']})
    glyf, metrics = {}, {}
    for g in glyphs:
        pen = TTGlyphPen(None)
        for (x, y, n) in runs_of(g['rows']):
            dx = slant_shift(y) if slant else 0
            if opt.primitive == 'runs':
                rect(pen, (x + dx) * PX, y * PX, (x + dx + n + smear) * PX, (y + 1) * PX)
            else:
                for px in range(x, x + n):
                    rounded_rect(pen, (px + dx) * PX, y * PX, (px + dx + 1 + smear) * PX,
                                 (y + 1) * PX, int(radius * PX))
        tt = pen.glyph()
        if tt.numberOfContours > 1:
            tt.flags[0] |= 0x40                    # OVERLAP_SIMPLE: overlaps are intended
        glyf[g['name']] = tt
        lsb = min(c[0] for c in tt.coordinates) if tt.numberOfContours else 0
        metrics[g['name']] = ((g['advance'] + smear) * PX, lsb)
    if '.notdef' not in glyf:
        pen = TTGlyphPen(None)
        rect(pen, PX, 0, 6 * PX, CAP * PX)
        glyf['.notdef'] = pen.glyph()
        metrics['.notdef'] = (7 * PX, PX)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASC * PX, descent=-DESC * PX, lineGap=0)
    ps = opt.family.replace(' ', '')
    fb.setupNameTable({
        'familyName': opt.family, 'styleName': style,
        'uniqueFontIdentifier': f'{opt.family} {style} {VERSION}',
        'fullName': f'{opt.family} {style}', 'psName': f'{ps}-{style.replace(" ", "")}',
        'version': f'Version {VERSION}',
    })
    fb.setupOS2(version=4, sTypoAscender=ASC * PX, sTypoDescender=-DESC * PX, sTypoLineGap=0,
                usWinAscent=ASC * PX, usWinDescent=DESC * PX, sxHeight=XHEIGHT * PX,
                sCapHeight=CAP * PX, fsSelection=0x80 | 0x40, fsType=0,
                achVendID='ARFT')
    fb.setupPost(isFixedPitch=0)
    fb.save(path)


glyphs = parse_sources(opt.glyphs)
ds = DesignSpaceDocument()
ds.addAxis(AxisDescriptor(tag='wght', name='Weight', minimum=400, default=400, maximum=700,
                          map=[(400, 0), (700, 1)]))
ds.addAxis(AxisDescriptor(tag='slnt', name='Slant', minimum=-18, default=0, maximum=0,
                          map=[(0, 0), (-18, 1)]))
if opt.primitive == 'pixels':
    ds.addAxis(AxisDescriptor(tag='ROND', name='Roundness', minimum=0, default=0, maximum=100,
                              map=[(0, 0), (100, 1)]))

# Sparse masters: every axis is independent, so one master per axis end is enough.
masters = [
    dict(style='Regular', smear=0, slant=0, radius=0, loc={'Weight': 0}),
    dict(style='Bold', smear=1, slant=0, radius=0, loc={'Weight': 1}),
    dict(style='Slanted', smear=0, slant=1, radius=0, loc={'Slant': 1}),
]
if opt.primitive == 'pixels':
    masters.append(dict(style='Round', smear=0, slant=0, radius=0.5, loc={'Roundness': 1}))
for m in masters:
    path = os.path.join(opt.out, f'master-{m["style"].lower()}.ttf')
    build_master(glyphs, smear=m['smear'], slant=m['slant'], radius=m['radius'],
                 style=m['style'], path=path)
    ds.addSource(SourceDescriptor(path=path, name=m['style'], location=m['loc'],
                                  familyName=opt.family, styleName=m['style']))
for style, w, s in [('Regular', 0, 0), ('Medium', 0.5, 0), ('Bold', 1, 0),
                    ('Italic', 0, 1), ('Bold Italic', 1, 1)]:
    ds.addInstance(InstanceDescriptor(familyName=opt.family, styleName=style,
                                      location={'Weight': w, 'Slant': s}))

vf, _, _ = varLib.build(ds)
vf['OS/2'].usWeightClass = 400
buildStatTable(vf, [
    {'tag': 'wght', 'name': 'Weight', 'values': [
        {'value': 400, 'name': 'Regular', 'flags': 0x2, 'linkedValue': 700},
        {'value': 500, 'name': 'Medium'},
        {'value': 700, 'name': 'Bold'}]},
    {'tag': 'slnt', 'name': 'Slant', 'values': [
        {'value': 0, 'name': 'Upright', 'flags': 0x2, 'linkedValue': -18},
        {'value': -18, 'name': 'Italic'}]},
] + ([{'tag': 'ROND', 'name': 'Roundness', 'values': [
        {'value': 0, 'name': 'Square', 'flags': 0x2},
        {'value': 100, 'name': 'Dots'}]}] if opt.primitive == 'pixels' else []))
with open(os.path.join(opt.out, 'charset.txt'), 'w') as fh:   # for the specimen page
    fh.write(''.join(chr(cp) for g in glyphs for cp in sorted(g['unicode']) if cp >= 0x20))
base = os.path.join(opt.out, f'{opt.family.replace(" ", "")}-VF')
vf.save(base + '.ttf')
vf.flavor = 'woff2'
vf.save(base + '.woff2')
print(f'{len(vf.getGlyphOrder())} glyphs, {opt.primitive}: '
      f'{os.path.getsize(base + ".ttf")} B ttf, {os.path.getsize(base + ".woff2")} B woff2')
