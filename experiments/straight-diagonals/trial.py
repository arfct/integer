"""Try the importer's redraw (scripts/diagonals.py) on a glyph tree without an import.

    .venv/bin/python experiments/straight-diagonals/trial.py [--root glyphs] [--parity off|avv|all] [--all] [--dump K:12:bold]

The committed drawings are what the erosion left, so the redraw can be run on
them directly; the hinted render is not at hand here, so the eroded drawing
stands in for it. Prints bent edges and kinks by letter, before and after.
"""
import argparse
import collections
import os
import sys

import lib
import measure
import diagonals

NAMES = {'7': 'seven', '/': 'slash', '\\': 'backslash', '<': 'less', '>': 'greater'}


def sheet(opt, grids):
    rows = []
    for g in grids:
        for w in opt.weights.split(','):
            meta, G = lib.load(g, w)
            row = []
            for ch in opt.letters:
                bm = lib.crop(G[ch]['bm'])
                out, status = diagonals.redraw(NAMES.get(ch, ch), bm, bm, meta['stem'], meta['bar'], opt.parity)
                s = 6 if g <= 13 else 4 if g <= 24 else 2
                row.append((f'{ch}', lib.plain(bm, s)))
                row.append((status, lib.plain(out, s)))
            rows.append(f'{g} {w} stem {meta["stem"]}')
            rows.append(row)
    print(lib.sheet(rows, opt.sheet, title=f'eroded / redrawn, parity {opt.parity}'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root')
    ap.add_argument('--parity', default='off')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--dump')
    ap.add_argument('--sheet', help='PNG: each letter before and after, one row a size')
    ap.add_argument('--weights', default='bold')
    ap.add_argument('--letters', default=measure.GLYPHS)
    opt = ap.parse_args()
    if opt.root:
        lib.set_root(opt.root)
    if opt.dump:
        ch, g, w = opt.dump.split(':')
        meta, G = lib.load(int(g), w)
        bm = lib.crop(G[ch]['bm'])
        out, status = diagonals.redraw(NAMES.get(ch, ch), bm, bm, meta['stem'], meta['bar'], opt.parity)
        print(status, diagonals.bent(bm, meta['stem']), diagonals.bent(out, meta['stem']))
        for y in range(bm.shape[0]):
            print(''.join('#' if v else '.' for v in bm[y]) + '   ' + (''.join('#' if v else '.' for v in out[y]) if y < out.shape[0] else ''))
        return
    grids = lib.ALL_GRIDS if opt.all else lib.GRIDS
    if opt.sheet:
        return sheet(opt, grids)
    per = collections.defaultdict(lambda: [collections.Counter(), collections.Counter()])
    stat = collections.defaultdict(collections.Counter)
    widths = collections.Counter()
    for g in grids:
        for w in lib.WEIGHTS:
            meta, G = lib.load(g, w)
            k, h = meta['stem'], meta['bar']
            for ch in measure.GLYPHS:
                bm = lib.crop(G[ch]['bm'])
                out, status = diagonals.redraw(NAMES.get(ch, ch), bm, bm, k, h, opt.parity)
                stat[ch][status] += 1
                per[ch][0].update(measure.tally(measure.score(bm, k)))
                per[ch][1].update(measure.tally(measure.score(out, k)))
                per[ch][0]['ink'] += int(bm.sum())
                per[ch][1]['ink'] += int(out.sum())
                if out.shape != bm.shape:
                    widths[ch] += 1
    tot = [collections.Counter(), collections.Counter()]
    print(f"{'':<3}{'edges':>6}{'bent':>6}{'kinks':>6}{'uneven':>7}{'thin':>6}{'ink':>7}   {'edges':>6}{'bent':>6}{'kinks':>6}{'uneven':>7}{'thin':>6}{'ink':>7}   status, widths changed")
    for ch in measure.GLYPHS:
        a, b = per[ch]
        tot[0].update(a)
        tot[1].update(b)
        print(f"{ch:<3}" + '   '.join(f"{c['edges']:>6}{c['bent']:>6}{c['kinks']:>6}{c['uneven']:>7}{c['thin']:>6}{c['ink']:>7}" for c in (a, b))
              + '   ' + ' '.join(f'{k} {v}' for k, v in sorted(stat[ch].items())) + (f'  width {widths[ch]}' if widths[ch] else ''))
    print(f"{'all':<3}" + '   '.join(f"{c['edges']:>6}{c['bent']:>6}{c['kinks']:>6}{c['uneven']:>7}{c['thin']:>6}{c['ink']:>7}" for c in tot))


if __name__ == '__main__':
    main()
