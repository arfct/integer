"""Stepped variable pixel font: every rendered instance is a real bitmap.

Masters are hand-drawn (or smeared) bitmaps on different grids; the axes are
made discrete with avar so the font never renders an interpolation.
  opsz 8..16  : 8-row drawing below 12, 16-row drawing from 12 up
  wght 400..700: 1px stems below 550, 2px from 550 up
"""
import os, re, sys
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor
from fontTools import varLib

UPM = 1600
out = sys.argv[1] if len(sys.argv) > 1 else 'out'
os.makedirs(out, exist_ok=True)

def parse(path):
    text = re.sub(r'^#.*\n?', '', open(path).read(), flags=re.M)
    glyphs = {}
    cur = None
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = [l for l in block.split('\n') if l]
        if lines[0].startswith('name:'):
            meta = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
            cur = glyphs[meta['name']] = {'unicode': [int(u[2:], 16) for u in meta.get('unicode', '').split()],
                                          'advance': int(meta['advance']), 'rows': []}
        else:
            cur['rows'] = lines
    return glyphs

def runs(rows, asc):
    r = []
    for i, line in enumerate(rows):
        y, x = asc - 1 - i, 0
        while x < len(line):
            if line[x] == '#':
                x0 = x
                while x < len(line) and line[x] == '#': x += 1
                r.append((x0, y, x - x0))
            else: x += 1
    return r

# (file, rows in em, ascent rows, design location)
masters = [
    ('sources/glyphs16.txt', 16, 13, {'Size': 1, 'Weight': 0}, 'Regular'),
    ('sources/glyphs16b.txt', 16, 13, {'Size': 1, 'Weight': 1}, 'Bold'),
    ('sources/glyphs8.txt', 8, 7, {'Size': 0, 'Weight': 0}, 'Small'),
    ('sources/glyphs8b.txt', 8, 7, {'Size': 0, 'Weight': 1}, 'Small Bold'),
]
srcs = [(parse(f), rows, asc, loc, style) for f, rows, asc, loc, style in masters]
names = [n for n in srcs[0][0] if n != '.notdef']
# Every master needs the same rectangle count per glyph: pad with zero-size rectangles.
count = {n: max(len(runs(g[n]['rows'], asc)) for g, rows, asc, _, _ in srcs if n in g) for n in names}

ds = DesignSpaceDocument()
ds.addAxis(AxisDescriptor(tag='opsz', name='Size', minimum=8, default=16, maximum=16,
                          map=[(8, 0), (11.99, 0), (12, 1), (16, 1)]))
ds.addAxis(AxisDescriptor(tag='wght', name='Weight', minimum=400, default=400, maximum=700,
                          map=[(400, 0), (549.99, 0), (550, 1), (700, 1)]))
for glyphs, rows, asc, loc, style in srcs:
    px = UPM // rows
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(['.notdef'] + names)
    fb.setupCharacterMap({cp: n for n in names for cp in srcs[0][0][n]['unicode']})
    glyf, metrics = {}, {}
    for n in names:
        g = glyphs.get(n) or srcs[0][0][n]
        pen = TTGlyphPen(None)
        rs = runs(g['rows'], asc)
        for (x, y, w) in rs + [(0, 0, 0)] * (count[n] - len(rs)):
            pen.moveTo((x * px, (y + 1) * px)); pen.lineTo(((x + w) * px, (y + 1) * px))
            pen.lineTo(((x + w) * px, y * px)); pen.lineTo((x * px, y * px)); pen.closePath()
        tt = pen.glyph()
        if tt.numberOfContours > 1: tt.flags[0] |= 0x40
        glyf[n] = tt
        metrics[n] = (g['advance'] * px, min((c[0] for c in tt.coordinates), default=0))
    pen = TTGlyphPen(None); pen.moveTo((100, 0)); pen.lineTo((600, 0)); pen.lineTo((600, 900)); pen.lineTo((100, 900)); pen.closePath()
    glyf['.notdef'] = pen.glyph(); metrics['.notdef'] = (700, 100)
    fb.setupGlyf(glyf); fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=asc * px, descent=-(rows - asc) * px, lineGap=0)
    fb.setupNameTable({'familyName': 'Integer', 'styleName': style})
    fb.setupOS2(version=4, sTypoAscender=asc * px, sTypoDescender=-(rows - asc) * px, sTypoLineGap=0,
                usWinAscent=asc * px, usWinDescent=(rows - asc) * px, fsSelection=0x40 | 0x80)
    fb.setupPost()
    p = os.path.join(out, f'master-{style.replace(" ", "-").lower()}.ttf'); fb.save(p)
    ds.addSource(SourceDescriptor(path=p, name=style, location=loc, familyName='Integer', styleName=style))
vf, _, _ = varLib.build(ds)
vf.save(os.path.join(out, 'IntegerStep-VF.ttf'))
vf.flavor = 'woff2'; vf.save(os.path.join(out, 'IntegerStep-VF.woff2'))
print('avar', {a: vf['avar'].segments[a] for a in vf['avar'].segments})
print('glyphs', len(names), 'woff2', os.path.getsize(os.path.join(out, 'IntegerStep-VF.woff2')), 'B')
