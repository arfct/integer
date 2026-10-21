"""File-size experiment: 4 grids x 2 weights in one stepped variable font.

    python experiments/size/build.py [MULT]

The 24- and 32-row grids are integer-scaled stand-ins for hand drawings, so
their rectangle counts are realistic. MULT copies the glyph set to estimate a
larger character set; copies are identical, so woff2 compresses them away and
only the TTF size and the 240-glyph woff2 scaled linearly are meaningful.
Measured 2026-10-20: 240 glyphs = 0.40 MB ttf, 43 KB woff2; 1200 glyphs =
2.0 MB ttf, so about 215 KB woff2 for 1200 distinct glyphs."""
import os, re, sys
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor
from fontTools import varLib
UPM = 1600; MULT = int(sys.argv[1]) if len(sys.argv) > 1 else 5
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'stepped', 'sources') + '/'
OUT = os.path.join(HERE, 'out')
def parse(path):
    text = re.sub(r'^#.*\n?', '', open(path).read(), flags=re.M); glyphs = {}; cur = None
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = [l for l in block.split('\n') if l]
        if lines[0].startswith('name:'):
            meta = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
            cur = glyphs[meta['name']] = {'unicode': [int(u[2:], 16) for u in meta.get('unicode', '').split()], 'advance': int(meta['advance']), 'rows': []}
        else: cur['rows'] = lines
    return glyphs
def scale(glyphs, k):
    return {n: {'unicode': g['unicode'], 'advance': g['advance'] * k, 'rows': [''.join(c * k for c in r) for r in g['rows'] for _ in range(k)]} for n, g in glyphs.items()}
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
g16, g16b, g8, g8b = (parse(SRC + f) for f in ['glyphs16.txt', 'glyphs16b.txt', 'glyphs8.txt', 'glyphs8b.txt'])
masters = [(g8, 8, 7, 0, 0), (g8b, 8, 7, 0, 1), (g16, 16, 13, 1, 0), (g16b, 16, 13, 1, 1),
           (scale(g8, 3), 24, 21, 2, 0), (scale(g8b, 3), 24, 21, 2, 1), (scale(g16, 2), 32, 26, 3, 0), (scale(g16b, 2), 32, 26, 3, 1)]
base = [n for n in g16 if n != '.notdef']
names = [f'{n}~{i}' if i else n for i in range(MULT) for n in base]
def src(glyphs, n): return glyphs[n.split('~')[0]]
count = {n: max(len(runs(src(g, n)['rows'], asc)) for g, _, asc, _, _ in masters) for n in names}
ds = DesignSpaceDocument()
ds.addAxis(AxisDescriptor(tag='opsz', name='Size', minimum=8, default=16, maximum=32, map=[(8, 0), (11.99, 0), (12, 1), (16, 1), (19.99, 1), (20, 2), (27.99, 2), (28, 3), (32, 3)]))
ds.addAxis(AxisDescriptor(tag='wght', name='Weight', minimum=400, default=400, maximum=700, map=[(400, 0), (549.99, 0), (550, 1), (700, 1)]))
os.makedirs(OUT, exist_ok=True)
for i, (glyphs, rows, asc, s, w) in enumerate(masters):
    px = UPM // rows; fb = FontBuilder(UPM, isTTF=True); fb.setupGlyphOrder(['.notdef'] + names)
    fb.setupCharacterMap({cp: n for n in base for cp in g16[n]['unicode']})
    glyf, metrics = {}, {}
    for n in names:
        g = src(glyphs, n); pen = TTGlyphPen(None); rs = runs(g['rows'], asc)
        for (x, y, wd) in rs + [(0, 0, 0)] * (count[n] - len(rs)):
            pen.moveTo((x * px, (y + 1) * px)); pen.lineTo(((x + wd) * px, (y + 1) * px)); pen.lineTo(((x + wd) * px, y * px)); pen.lineTo((x * px, y * px)); pen.closePath()
        tt = pen.glyph(); glyf[n] = tt; metrics[n] = (g['advance'] * px, 0)
    pen = TTGlyphPen(None); pen.moveTo((100, 0)); pen.lineTo((600, 0)); pen.lineTo((600, 900)); pen.lineTo((100, 900)); pen.closePath()
    glyf['.notdef'] = pen.glyph(); metrics['.notdef'] = (700, 100)
    fb.setupGlyf(glyf); fb.setupHorizontalMetrics(metrics); fb.setupHorizontalHeader(ascent=asc * px, descent=-(rows - asc) * px)
    fb.setupNameTable({'familyName': 'Size Test', 'styleName': f'm{i}'}); fb.setupOS2(); fb.setupPost()
    p = os.path.join(OUT, f'm{i}.ttf'); fb.save(p)
    ds.addSource(SourceDescriptor(path=p, name=f'm{i}', location={'Size': s, 'Weight': w}))
vf, _, _ = varLib.build(ds)
vf.save(os.path.join(OUT, 'SizeTest-VF.ttf')); vf.flavor = 'woff2'; vf.save(os.path.join(OUT, 'SizeTest-VF.woff2'))
tot = sum(count.values())
print(f'{len(names)} glyphs, 8 masters (4 grids x 2 weights), {tot} rectangles/master; ttf {os.path.getsize(os.path.join(OUT, "SizeTest-VF.ttf"))/1e6:.2f} MB, woff2 {os.path.getsize(os.path.join(OUT, "SizeTest-VF.woff2"))/1e3:.0f} KB')
