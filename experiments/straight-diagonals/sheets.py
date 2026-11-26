"""Sheets comparing glyph trees: the same text set from each, one row a tree.

    .venv/bin/python experiments/straight-diagonals/sheets.py --roots before=PATH after=glyphs \\
        --grids 9,12,16 --weights bold --text diag|alpha|"any text" --out img/name.png [--scale 0]

One block per grid and weight; scale 0 picks a magnification by size.
"""
import argparse

import lib

TEXTS = {
    'diag': 'AVvWwXxYyKkMNZz7/\\<>',
    'alpha': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789',
    'bars': 'EFHTLZBPRS easzftg 2357 +-=',
    'proof': 'AVAVA vavav WAVY wavy MIXTAPE KNOX Hamburgefonstiv',
}


def scale_for(grid, n):
    s = 8 if grid <= 13 else 6 if grid <= 24 else 4 if grid <= 32 else 3
    return max(2, s // 2) if n > 30 else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--roots', nargs='+', required=True)
    ap.add_argument('--grids', default='9,12,16,20,24,32,48')
    ap.add_argument('--weights', default='light,regular,bold')
    ap.add_argument('--text', default='diag')
    ap.add_argument('--out', required=True)
    ap.add_argument('--scale', type=int, default=0)
    ap.add_argument('--title')
    opt = ap.parse_args()
    text = TEXTS.get(opt.text, opt.text)
    rows = []
    for g in [int(x) for x in opt.grids.split(',')]:
        for w in opt.weights.split(','):
            first = True
            for r in opt.roots:
                label, path = r.split('=', 1)
                lib.set_root(path)
                meta, _ = lib.load(g, w)
                if first:
                    rows.append(f"{g} {w}")
                    first = False
                bm = lib.text_bitmap(g, w, text)
                s = opt.scale or scale_for(g, len(text))
                rows.append([(f"{label}: stem {meta['stem']} bar {meta['bar']}", lib.plain(bm, s))])
    print(lib.sheet(rows, opt.out, title=opt.title or f'{opt.text}: ' + ' / '.join(r.split('=')[0] for r in opt.roots)))


if __name__ == '__main__':
    main()
