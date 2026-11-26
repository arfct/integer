"""Measure how straight the diagonal strokes of the committed drawings are.

    .venv/bin/python experiments/straight-diagonals/measure.py            # the ten grids of the study
    .venv/bin/python experiments/straight-diagonals/measure.py --all      # grids 7 to 48
    .venv/bin/python experiments/straight-diagonals/measure.py --glyph A  # one letter, every edge listed

An edge is a sequence x(y): the column of one side of a stroke in consecutive
rows. Two kinds are taken from a bitmap, with no knowledge of the letter:

  outer   the left silhouette (first ink column per row) and the right one,
          cut where the silhouette turns round (the waist of X, the crotch of
          K: it retraces 2 or more columns), wherever it jumps 3 or more
          columns in one row (from a bar onto a diagonal, as in Z and 7), and
          with a flat end dropped when it is a stem (3+ rows and twice any
          other run: the stem of Y)
  inner   both sides of a run that is neither first nor last in its row,
          followed from row to row while it stays one run (the middle strokes
          of W, the V of M, the diagonal of N)

An edge counts as a diagonal when it spans 4 or more rows and 2 or more
columns. Each one is scored:

  strip    the least w such that every x(y) lies in a band s*y + c .. s*y + c + w
           for some slope s, measured across the edge's minor axis (columns on
           a steep edge, rows on a shallow one). An edge is a digital straight
           line exactly when strip < 1: that is the definition of one.
           strip - 1, floored at 0, is how far the edge leaves the best
           straight line, in pixels.
  bow      mean of x(y) minus the chord between the edge's two ends, signed so
           that positive is toward the letter's centre column: a positive bow
           on A is the leg pulled in at mid-height and flared at the foot.
  runs     lengths of the stretches of constant x (rows per column) on a steep
           edge, or the column steps per row on a shallow one
  kink     a run 2 or more longer or shorter than both its neighbours (1-3-1)
  uneven   interior runs (first and last left out, they may be cut short by
           the stroke's end) that differ by 2 or more
  back     a step against the edge's direction: the silhouette moves out and
           back in

`thin` counts rows of an outer diagonal whose run is narrower than the stem.
"""
import argparse
import collections
import os
import sys

import numpy as np

import lib

GLYPHS = 'AVvWwXxYyKkMNZz7/\\<>'
SYM = set('AVvWwXxY')


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'scripts'))
from diagonals import (row_runs, split_jumps, pivots, strip_ends, segments, outer_edges, inner_edges,   # noqa: E402,F401
                       strip, run_lengths, kinks, score_edge, score)


def tally(scores):
    c = collections.Counter()
    for s in scores:
        c['edges'] += 1
        c['bent'] += not s['straight']
        c['excess'] += max(0.0, s['strip'] - 1)
        c['kinks'] += s['kinks']
        c['uneven'] += bool(s['uneven'])
        c['back'] += s['back']
        c['thin'] += s['thin']
        c['absbow'] += abs(s['bow'])
    return c


def line(label, c):
    n = max(1, c['edges'])
    return (f"{label:<14}{c['edges']:>6}{c['bent']:>6}{100 * c['bent'] / n:>7.1f}%{c['excess'] / n:>8.2f}"
            f"{c['kinks']:>7}{c['uneven']:>8}{c['back']:>6}{c['thin']:>6}")


HEAD = f"{'':<14}{'edges':>6}{'bent':>6}{'':>8}{'excess':>8}{'kinks':>7}{'uneven':>8}{'back':>6}{'thin':>6}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--glyph')
    ap.add_argument('--glyphs', default=GLYPHS)
    ap.add_argument('--root', help='another glyph tree than glyphs/')
    opt = ap.parse_args()
    if opt.root:
        lib.set_root(opt.root)
    grids = lib.ALL_GRIDS if opt.all else lib.GRIDS
    if opt.glyph:
        for g in grids:
            for w in lib.WEIGHTS:
                meta, G = lib.load(g, w)
                for s in score(G[opt.glyph]['bm'], meta['stem']):
                    print(f"{g:>2} {w:<8} {s['kind']} {s['side']} rows {s['y0']}-{s['y1']} dx {s['dx']} strip {s['strip']:.2f} "
                          f"bow {s['bow']:+.2f} {s['unit']} {'-'.join(map(str, s['runs']))}"
                          + (' KINK' if s['kinks'] else '') + (' BACK' if s['back'] else ''))
        return
    by_size, by_glyph, by_weight, total = {}, collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), collections.Counter()
    bows = collections.defaultdict(list)
    for g in grids:
        for w in lib.WEIGHTS:
            meta, G = lib.load(g, w)
            c = collections.Counter()
            for ch in opt.glyphs:
                if ch not in G:
                    continue
                sc = score(G[ch]['bm'], meta['stem'])
                t = tally(sc)
                c.update(t)
                by_glyph[ch].update(t)
                by_glyph[ch]['drawings'] += 1
                by_glyph[ch]['bent drawings'] += t['bent'] > 0
                for s in sc:
                    if s['kind'] == 'outer' and ch in 'AVv' and s['rows'] >= 0.8 * lib.crop(G[ch]['bm']).shape[0]:
                        bows[(ch, w)].append(s['bow'])
                c['drawings'] += 1
                c['bent drawings'] += t['bent'] > 0
            by_size[(g, w)] = c
            by_weight[w].update(c)
            total.update(c)
    print(f'Diagonal edges of {opt.glyphs} at grids {grids[0]} to {grids[-1]} ({len(grids)} grids); bent = not a digital straight line;')
    print('excess = mean pixels outside the best straight band; kinks = 1-3-1 runs; uneven = interior runs differing by 2+;')
    print('back = steps against the direction; thin = rows of an outer diagonal narrower than the stem\n')
    print(HEAD)
    for (g, w), c in by_size.items():
        print(line(f'{g} {w}', c))
    print()
    for w in lib.WEIGHTS:
        print(line(w, by_weight[w]))
    print(line('all', total))
    print(f"\ndrawings with a bent edge: {total['bent drawings']} of {total['drawings']}")
    print('\nBy letter')
    print(HEAD + '   drawings with a bent edge')
    for ch in opt.glyphs:
        c = by_glyph[ch]
        print(line(ch, c) + f"   {c['bent drawings']} of {c['drawings']}")
    print('\nBow of the full-height outer legs of A, V, v, in pixels, positive toward the centre column (mean, and how many each way)')
    for (ch, w), v in sorted(bows.items()):
        print(f"  {ch} {w:<8} n {len(v):>3}  mean {np.mean(v):+.2f}  toward centre {sum(1 for b in v if b > 0.1):>3}  away {sum(1 for b in v if b < -0.1):>3}")


if __name__ == '__main__':
    sys.exit(main())
