"""Print committed drawings side by side as text, for reading.

    .venv/bin/python experiments/straight-diagonals/dump.py AVvn 12,16,20 regular,bold
"""
import sys

import lib

chars = sys.argv[1]
grids = [int(g) for g in sys.argv[2].split(',')]
weights = sys.argv[3].split(',') if len(sys.argv) > 3 else lib.WEIGHTS
for g in grids:
    for w in weights:
        meta, G = lib.load(g, w)
        cells = []
        for ch in chars:
            bm = G[ch]['bm']
            b = lib.ink_box(bm)
            c = bm[b[0]:b[1] + 1, b[2]:b[3] + 1]
            cells.append([''.join('#' if v else '.' for v in r) for r in c])
        print(f'--- {g} {w} ({meta["note"]}) cap {meta["cap"]} x {meta["xheight"]}')
        h = max(len(c) for c in cells)
        cells = [[' ' * len(c[0])] * (h - len(c)) + c for c in cells]
        for i in range(h):
            print('   '.join(c[i] for c in cells))
