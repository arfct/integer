"""Is the weight the same across the characters of one size and weight?

    .venv/bin/python experiments/straight-diagonals/weight.py [--root glyphs] [--json out.json] [--glyph W:12:bold]

One instance is one grid in one weight (12 Bold). Its nominal strokes are the
stem and bar in the file's header. For every printable ASCII and Latin-1
drawing the strokes are found and measured:

  stem      a straight run of rows whose ink run stays in place (it moves
            under 0.15 columns a row), at least 3 rows and taller than it is
            wide. Thickness is the run's length.
  bar       the same thing read down the columns: a flat run of columns.
            Thickness is the column run's length.
  diagonal  on the glyphs the source draws with a straight diagonal (DIAG):
            a straight run of rows whose ink run moves by 2+ columns in all,
            4+ rows and at least 0.3 of the drawing's height (or, read down
            the columns, a shallow one, against its width).
            Thickness is measured across the stroke: the mean run length
            divided by sqrt(1 + slope^2), which is the stroke's ink per unit
            of its length. A 45 degree stroke of one pixel a row is 0.71.
  round     for the round letters, the stroke at the ink box's extremes: the
            shortest column run under the top row's ink and over the
            bottom row's (against the bar) and the shortest row run inside
            the left and right columns' ink (against the stem).
  density   ink pixels over the advance, relative to the instance's median
            over A-Z a-z 0-9, then relative to the same letter's median of
            that figure over every grid of the weight: a letter that is
            lighter or darker in this instance than it usually is.

A stroke deviates when it is more than 0.5 px off the nominal stem (stems,
diagonals, the sides of rounds) or bar (bars, the tops and bottoms of
rounds); a density deviates when it is more than 20% off. `bar<stem` counts
the glyphs with a bar more than 0.5 px under the stem, whatever the header
says the bar is: the other reading of a Bold that looks one pixel tall.

A run of rows is a chain: a run linked to the one run it touches in the next
row. It breaks where a run touches two (a join), and where the length changes
by 2 or more (a bar, a corner). A chain is straight when no run's centre is
over a pixel off the line between its ends and, the end rows aside, its run
lengths differ by at most 1; a chain that is not straight is a curve and is
not measured here.
"""
import argparse
import collections
import json
import math
import os
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib          # noqa: E402

CHARS = [chr(c) for c in list(range(0x21, 0x7F)) + list(range(0xA1, 0x100)) if c != 0xAD]
ALNUM = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')
ROUND = {'top': 'OoQ0CcGeSs8369', 'bottom': 'OoQ0CcGeSs8369Uu', 'left': 'OoQ0CcGeqd', 'right': 'OoQ0Dbp'}
DIAG = set('AVvWwXxYyKkMNZz7/\\<>4R\u00c0\u00c1\u00c2\u00c3\u00c4\u00c5\u00dd\u00fd\u00ff\u00d7')
BANDS = ((7, 12), (13, 16), (17, 24), (25, 48))
KINDS = ('stem', 'bar', 'diagonal', 'round', 'density')


def runs(row):
    out, x, n = [], 0, len(row)
    while x < n:
        if row[x]:
            a = x
            while x < n and row[x]:
                x += 1
            out.append((a, x - 1))
        else:
            x += 1
    return out


def chains(bm):
    """Chains of runs down the rows: [(y, a, b), ...], one run a row."""
    rr = [runs(r) for r in bm]
    out, open_ = [], {}                      # open_: (y, a, b) of a chain's last run -> the chain
    for y, row in enumerate(rr):
        prev = rr[y - 1] if y else []
        nxt = {}
        for a, b in row:
            ups = [p for p in prev if p[0] <= b + 1 and p[1] >= a - 1]
            c = None
            if len(ups) == 1:
                p = ups[0]
                downs = [q for q in row if q[0] <= p[1] + 1 and q[1] >= p[0] - 1]
                if len(downs) == 1 and abs((b - a) - (p[1] - p[0])) <= 1:
                    c = open_.get((y - 1,) + p)
            if c is None:
                c = []
                out.append(c)
            c.append((y, a, b))
            nxt[(y, a, b)] = c
        open_ = nxt
    return out


def straight(c):
    """(slope in columns a row, mean run length) of a straight chain, or None."""
    n = len(c)
    mid = [(a + b) / 2 for _, a, b in c]
    s = (mid[-1] - mid[0]) / (n - 1)
    if any(abs(m - (mid[0] + s * i)) > 1.0 for i, m in enumerate(mid)):
        return None
    lens = [b - a + 1 for _, a, b in c]
    core = lens[1:-1] if n > 3 else lens
    if max(core) - min(core) > 1:
        return None
    return s, statistics.mean(core)


def strokes(bm, diagonals=True):
    """[(kind, thickness, rows or columns), ...] for one cropped drawing."""
    out = []
    for flip, flat, steep in ((False, 'stem', 1.0), (True, 'bar', 0.999)):
        m = bm.T if flip else bm
        for c in chains(m):
            n = len(c)
            if n < 3:
                continue
            st = straight(c)
            if st is None:
                continue
            s, w = st
            if abs(s) < 0.15:
                if n > w:
                    out.append((flat, w, n))
            elif diagonals and n >= max(4, 0.3 * m.shape[0]) and abs(s) * (n - 1) >= 2 and abs(s) <= steep and n > w:
                out.append(('diagonal', w / math.sqrt(1 + s * s), n))
    return out


def extremes(ch, bm):
    """[(side, thickness)] for a round letter."""
    out = []
    H, W = bm.shape
    for side, flip, far in (('top', False, False), ('bottom', False, True), ('left', True, False), ('right', True, True)):
        if ch not in ROUND[side]:
            continue
        m = bm.T if flip else bm
        if far:
            m = m[::-1]
        r = runs(m[0])
        if not r:
            continue
        a, b = max(r, key=lambda t: t[1] - t[0])
        best = None
        for x in range(a, b + 1):
            n = 0
            while n < m.shape[0] and m[n, x]:
                n += 1
            best = n if best is None else min(best, n)
        out.append((side, best))
    return out


def measure(root, grids=lib.ALL_GRIDS):
    lib.set_root(root)
    data = {}
    for grid in grids:
        for weight in lib.WEIGHTS:
            meta, G = lib.load(grid, weight)
            k, h = meta['stem'], meta['bar']
            inst = {'stem': k, 'bar': h, 'glyphs': {}}
            dens = {}
            for ch in CHARS:
                g = G.get(ch)
                if g is None:
                    continue
                bm = lib.crop(g['bm'])
                if not bm.size:
                    continue
                st = strokes(bm, ch in DIAG)
                e = {'stem': [w for kind, w, _ in st if kind == 'stem'],
                     'bar': [w for kind, w, _ in st if kind == 'bar'],
                     'diagonal': [round(w, 2) for kind, w, _ in st if kind == 'diagonal'],
                     'round': extremes(ch, bm),
                     'ink': int(bm.sum()), 'advance': g['advance']}
                inst['glyphs'][ch] = e
                if ch in ALNUM and g['advance']:
                    dens[ch] = e['ink'] / g['advance']
            med = statistics.median(dens.values()) if dens else 1
            for ch, e in inst['glyphs'].items():
                e['rel'] = (e['ink'] / e['advance'] / med) if e['advance'] else None
            data[(grid, weight)] = inst
    norm = collections.defaultdict(list)
    for (grid, weight), inst in data.items():
        for ch, e in inst['glyphs'].items():
            if e['rel']:
                norm[(ch, weight)].append(e['rel'])
    norm = {key: statistics.median(v) for key, v in norm.items()}
    for (grid, weight), inst in data.items():
        k, h = inst['stem'], inst['bar']
        for ch, e in inst['glyphs'].items():
            dev = {}
            off = [w - k for w in e['stem'] if abs(w - k) > 0.5]
            if off:
                dev['stem'] = max(off, key=abs)
            off = [w - h for w in e['bar'] if abs(w - h) > 0.5]
            if off:
                dev['bar'] = max(off, key=abs)
            off = [w - k for w in e['diagonal'] if abs(w - k) > 0.5]
            if off:
                dev['diagonal'] = round(max(off, key=abs), 2)
            off = [w - (h if side in ('top', 'bottom') else k) for side, w in e['round']
                   if abs(w - (h if side in ('top', 'bottom') else k)) > 0.5]
            if off:
                dev['round'] = max(off, key=abs)
            if ch in ALNUM and e['rel'] and norm.get((ch, weight)):
                r = e['rel'] / norm[(ch, weight)]
                if abs(r - 1) > 0.20:
                    dev['density'] = round(r - 1, 2)
            if any(w < k - 0.5 for w in e['bar']):
                dev['bar<stem'] = True
            if any(w < k - 0.5 for w in e['diagonal']):
                dev['diag<stem'] = True
            e['dev'] = dev
    return data


COLS = KINDS + ('bar<stem', 'diag<stem', 'any')


def count(insts, scope=None):
    c = collections.Counter()
    for inst in insts:
        for ch, e in inst['glyphs'].items():
            if scope and ch not in scope:
                continue
            c['glyphs'] += 1
            for kind in KINDS + ('bar<stem', 'diag<stem'):
                c[kind] += kind in e['dev']
            c['any'] += any(kind in e['dev'] for kind in KINDS)
    return c


def row(label, c):
    return f'{label:<16}{c["glyphs"]:>7}' + ''.join(f'{c[k]:>10}' for k in COLS)


def report(data, out=sys.stdout):
    p = lambda *a: print(*a, file=out)
    grids = sorted({g for g, _ in data})
    p(f'Weight consistency, grids {grids[0]} to {grids[-1]}, printable ASCII and Latin-1: glyphs with a deviating stroke')
    head = f'{"":<16}{"glyphs":>7}' + ''.join(f'{k:>10}' for k in COLS)
    for title, scope in (('letters and digits (A-Z a-z 0-9)', ALNUM), ('every glyph', None)):
        p(f'\nBy weight, {title}\n' + head)
        for w in lib.WEIGHTS:
            p(row(w, count((i for (g, ww), i in data.items() if ww == w), scope)))
        p(row('all', count(data.values(), scope)))
        p(f'\nBy size band, {title}\n' + head)
        for lo, hi in BANDS:
            for w in lib.WEIGHTS:
                p(row(f'{lo}-{hi} {w}', count((i for (g, ww), i in data.items() if ww == w and lo <= g <= hi), scope)))
    p('\nBy instance (nominal stem/bar), letters and digits\n' + head)
    for (g, w), inst in sorted(data.items(), key=lambda t: (lib.WEIGHTS.index(t[0][1]), t[0][0])):
        p(row(f'{g} {w} {inst["stem"]}/{inst["bar"]}', count([inst], ALNUM)))
    p('\nWorst instances, by glyphs with any deviating stroke, and their worst glyphs')
    worst = sorted(data.items(), key=lambda t: -count([t[1]], ALNUM)['any'])[:15]
    for (g, w), inst in worst:
        bad = sorted(((sum(abs(v) for kk, v in e['dev'].items() if kk in KINDS), ch, e['dev'])
                      for ch, e in inst['glyphs'].items() if ch in ALNUM and any(kk in e['dev'] for kk in KINDS)), key=lambda t: -t[0])[:14]
        p(f'{g} {w} (stem {inst["stem"]}, bar {inst["bar"]}): {count([inst], ALNUM)["any"]} of {count([inst], ALNUM)["glyphs"]} letters and digits: '
          + '  '.join(f'{ch} ' + ','.join(f'{kk} {v:+g}' for kk, v in d.items() if kk in KINDS) for _, ch, d in bad))
    p('\nBy letter: glyphs with a deviating diagonal, all instances (top 24)')
    by = collections.Counter(ch for inst in data.values() for ch, e in inst['glyphs'].items() if 'diagonal' in e['dev'])
    p('  '.join(f'{ch} {n}' for ch, n in by.most_common(24)))
    p('By letter: glyphs with a deviating bar (top 24)')
    by = collections.Counter(ch for inst in data.values() for ch, e in inst['glyphs'].items() if 'bar' in e['dev'])
    p('  '.join(f'{ch} {n}' for ch, n in by.most_common(24)))
    p('By letter: glyphs with a deviating stem (top 24)')
    by = collections.Counter(ch for inst in data.values() for ch, e in inst['glyphs'].items() if 'stem' in e['dev'])
    p('  '.join(f'{ch} {n}' for ch, n in by.most_common(24)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=lib.GLYPHS)
    ap.add_argument('--json')
    ap.add_argument('--grids', help='e.g. 9,12,16 (default: all)')
    ap.add_argument('--glyph', help='letter:grid:weight, print what was measured')
    opt = ap.parse_args()
    grids = [int(g) for g in opt.grids.split(',')] if opt.grids else lib.ALL_GRIDS
    if opt.glyph:
        ch, grid, weight = opt.glyph.split(':')
        data = measure(opt.root)
        e = data[(int(grid), weight)]['glyphs'][ch]
        print(json.dumps(e, ensure_ascii=False))
        print('\n'.join(''.join('#' if v else '.' for v in r) for r in lib.crop(lib.load(int(grid), weight)[1][ch]['bm'])))
        return
    data = measure(opt.root, grids)
    report(data)
    if opt.json:
        json.dump({f'{g} {w}': inst for (g, w), inst in data.items()}, open(opt.json, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
