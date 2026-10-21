"""Rasterize a 16-grid pixel font (a static TTF/WOFF2) back to the text bitmap
source format: python scripts/import-pixel-operator.py font.woff2 > glyphs/x.txt

Samples the centre of every grid cell against the outlines, so it works on
any pixel font drawn with 100 units per pixel on a 1600-unit em."""
import sys
from fontTools.ttLib import TTFont
from fontTools.pens.pointInsidePen import PointInsidePen

ASC, DESC = 13, 3
f = TTFont(sys.argv[1])
PX = f['head'].unitsPerEm // 16
gs, hm, cmap = f.getGlyphSet(), f['hmtx'], f.getBestCmap()
rev = {}
for cp, g in cmap.items():
    rev.setdefault(g, []).append(cp)
out = []
for name in f.getGlyphOrder():
    adv, g, rows = hm[name][0] // PX, gs[name], []
    for row in range(ASC - 1, -DESC - 1, -1):
        line = ''
        for col in range(max(adv, 1) + 1):
            pen = PointInsidePen(gs, (col * PX + PX / 2, row * PX + PX / 2))
            g.draw(pen)
            line += '#' if pen.getResult() else '.'
        rows.append(line)
    cps = ' '.join(f'U+{c:04X}' for c in sorted(rev.get(name, [])))
    out.append(f'name: {name}\nunicode: {cps}\nadvance: {adv}\n\n' + '\n'.join(rows) + '\n')
print('\n'.join(out), end='')
