"""Print drawings from glyph trees side by side as text.

    .venv/bin/python experiments/straight-diagonals/show.py A:12:bold W:12:bold --roots glyphs PATH ...
"""
import argparse

import lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('glyphs', nargs='+', help='letter:grid:weight')
    ap.add_argument('--roots', nargs='+', default=[lib.GLYPHS])
    opt = ap.parse_args()
    for spec in opt.glyphs:
        ch, g, w = spec.rsplit(':', 2)
        cols, advs = [], []
        for r in opt.roots:
            lib.set_root(r)
            G = lib.load(int(g), w)[1]
            bm = lib.crop(G[ch]['bm'])
            cols.append([''.join('#' if v else '.' for v in row) for row in bm])
            advs.append(G[ch]['advance'])
        print(spec, 'advance', advs)
        for y in range(max(len(c) for c in cols)):
            print('   '.join((c[y] if y < len(c) else '').ljust(len(c[0])) for c in cols))


if __name__ == '__main__':
    main()
