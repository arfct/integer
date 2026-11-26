"""Compare two glyph trees: what a change to the importer did to the drawings.

    .venv/bin/python experiments/straight-diagonals/compare.py BEFORE AFTER [--list] [--grids 9,12,16]

Counts, over every grid and weight and every drawing in the files:
  drawings changed    ink or advance differs
  pixels changed      pixels that differ, drawings aligned on their origin
  advances changed    by letter, with the direction
  apex wider than a leg
                      A, V, v: the ink of the apex row against the leg's run
                      on the middle row; wider means the apex is doubled
                      (two legs side by side, or a flat of two strokes)
  symmetric letters   A H I M O T U V W X Y i l o v w x and the like must
                      mirror left to right: drawings that do not
"""
import argparse
import collections

import numpy as np

import lib
from diagonals import row_runs

SYM = 'AHIMOTUVWXYilovwx'
BANDS = ((7, 12), (13, 16), (17, 24), (25, 48))


def placed(g, w, h):
    a = np.zeros((h, w + 8), bool)
    bm = g['bm']
    x0 = g['left'] + 4
    a[:bm.shape[0], x0:x0 + bm.shape[1]] = bm[:h]
    return a


def apex_excess(bm, up):
    bm = lib.crop(bm)
    if not bm.size:
        return 0
    if not up:
        bm = bm[::-1]
    mid = row_runs(bm[bm.shape[0] // 2])
    leg = mid[0][1] - mid[0][0] + 1
    return int(bm[0].sum()) - leg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('before')
    ap.add_argument('after')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--grids', help='e.g. 9,12,16 (default: all)')
    opt = ap.parse_args()
    C = collections.Counter()
    adv = collections.defaultdict(collections.Counter)
    apex = {'before': collections.Counter(), 'after': collections.Counter()}
    asym = {'before': collections.Counter(), 'after': collections.Counter()}
    changed_by = collections.Counter()
    for g in ([int(x) for x in opt.grids.split(',')] if opt.grids else lib.ALL_GRIDS):
        for w in lib.WEIGHTS:
            lib.set_root(opt.before)
            ma, A = lib.load(g, w)
            lib.set_root(opt.after)
            mb, B = lib.load(g, w)
            band = next(f'{a}-{b}' for a, b in BANDS if a <= g <= b)
            for key in ('ascent', 'descent', 'above', 'cap', 'xheight'):
                if ma[key] != mb[key]:
                    C[f'metric {key} changed'] += 1
            for label, G, m in (('before', A, ma), ('after', B, mb)):
                for ch in 'AVv':
                    if apex_excess(G[ch]['bm'], ch == 'A') > 0:
                        apex[label][w] += 1
                        apex[label][band] += 1
                        apex[label]['all'] += 1
                for ch in SYM:
                    bm = lib.crop(G[ch]['bm'])
                    if bm.size and not (bm == bm[:, ::-1]).all():
                        asym[label]['all'] += 1
                        asym[label][ch] += 1
            for ch in A:
                if ch not in B:
                    C['missing after'] += 1
                    continue
                C['drawings'] += 1
                a, b = A[ch], B[ch]
                h = max(a['bm'].shape[0], b['bm'].shape[0])
                wd = max(a['bm'].shape[1] + a['left'], b['bm'].shape[1] + b['left'], 1) + 4
                pa, pb = placed(a, wd, h), placed(b, wd, h)
                n = int((pa ^ pb).sum())
                if n or a['advance'] != b['advance']:
                    C['drawings changed'] += 1
                    C[f'drawings changed {w}'] += 1
                    C[f'drawings changed {band}'] += 1
                    changed_by[ch] += 1
                C['pixels changed'] += n
                C[f'pixels changed {w}'] += n
                C['ink before'] += int(pa.sum())
                C['ink after'] += int(pb.sum())
                if a['advance'] != b['advance']:
                    C['advances changed'] += 1
                    adv[ch]['wider' if b['advance'] > a['advance'] else 'narrower'] += 1
                    if opt.list:
                        print(f"  advance {ch!r} {g} {w}: {a['advance']} -> {b['advance']}")
    for k in sorted(C):
        print(f'{k:<32}{C[k]:>9}')
    print('advances changed by letter: ' + (', '.join(f'{ch} {dict(v)}' for ch, v in sorted(adv.items())) or 'none'))
    print('drawings changed by letter (top 40): ' + ' '.join(f'{ch}:{n}' for ch, n in changed_by.most_common(40)))
    print(f'letters with a changed drawing: {len(changed_by)}')
    for label in ('before', 'after'):
        print(f'apex wider than a leg, A V v, {label}: ' + ', '.join(f'{k} {v}' for k, v in sorted(apex[label].items(), key=str)))
        print(f'symmetric letters not mirror-symmetric, {label}: ' + (', '.join(f'{k} {v}' for k, v in sorted(asym[label].items())) or '0'))


if __name__ == '__main__':
    main()
