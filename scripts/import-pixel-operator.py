import sys
from fontTools.ttLib import TTFont
from fontTools.pens.pointInsidePen import PointInsidePen
src, rows_total = sys.argv[1], int(sys.argv[2])
f = TTFont(src); PX = f['head'].unitsPerEm // rows_total
ASC = f['hhea'].ascent // PX; DESC = rows_total - ASC
gs, hm, cmap = f.getGlyphSet(), f['hmtx'], f.getBestCmap()
rev = {}
for cp, g in cmap.items(): rev.setdefault(g, []).append(cp)
out = []
for name in f.getGlyphOrder():
    adv, g, rows = hm[name][0] // PX, gs[name], []
    for row in range(ASC - 1, -DESC - 1, -1):
        line = ''
        for col in range(max(adv, 1) + 1):
            pen = PointInsidePen(gs, (col * PX + PX / 2, row * PX + PX / 2)); g.draw(pen)
            line += '#' if pen.getResult() else '.'
        rows.append(line)
    cps = ' '.join(f'U+{c:04X}' for c in sorted(rev.get(name, [])))
    out.append(f'name: {name}\nunicode: {cps}\nadvance: {adv}\n\n' + '\n'.join(rows) + '\n')
print(f'# grid {rows_total} asc {ASC} desc {DESC}')
print('\n'.join(out), end='')
