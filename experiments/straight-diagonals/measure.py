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
import sys

import numpy as np

import lib

GLYPHS = 'AVvWwXxYyKkMNZz7/\\<>'
SYM = set('AVvWwXxY')


def row_runs(row):
    """[(start, end)] inclusive, for one row of booleans."""
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


def split_jumps(ys, xs):
    """Cut an edge where it moves 3+ columns in one row and that is 3+ times its median step."""
    steps = [abs(b - a) for a, b in zip(xs, xs[1:])]
    med = sorted(steps)[len(steps) // 2] if steps else 0
    pieces, a = [], 0
    for i, s in enumerate(steps):
        if s >= 3 and s >= 3 * max(1, med):
            pieces.append((ys[a:i + 1], xs[a:i + 1]))
            a = i + 1
    pieces.append((ys[a:], xs[a:]))
    return pieces


def pivots(xs, need=2):
    """Indices where an edge turns round: it retraces `need` or more columns
    from an extreme. A single column out and back is a wobble, not a turn."""
    out, trend, ext, at = [], 0, xs[0], 0
    lo, lo_at, hi, hi_at = xs[0], 0, xs[0], 0
    for i, x in enumerate(xs):
        if trend == 0:
            if x < lo:
                lo, lo_at = x, i
            if x > hi:
                hi, hi_at = x, i
            if hi - lo >= need:
                trend = 1 if hi_at > lo_at else -1
                ext, at = (hi, hi_at) if trend > 0 else (lo, lo_at)
                first = lo_at if trend > 0 else hi_at
                if first > 0 and abs(xs[first] - xs[0]) >= need:
                    out.append(first)
            continue
        if (x - ext) * trend >= 0:
            if x != ext:
                ext, at = x, i
        elif (ext - x) * trend >= need:
            last = at
            while last + 1 < len(xs) and xs[last + 1] == ext:
                last += 1
            out.append((at + last) // 2)
            trend, ext, at = -trend, x, i
    return out


def strip_ends(ys, xs, wid):
    """Drop a flat end at least twice as long as every other run and 3+ rows:
    the stem a diagonal runs into (Y, K), not part of the diagonal."""
    for _ in range(2):
        seq, unit = run_lengths(xs)
        if unit != 'rows' or len(seq) < 3:
            break
        if seq[-1] >= 3 and seq[-1] >= 2 * max(seq[:-1]):
            n = len(xs) - seq[-1] + 1
            ys, xs, wid = ys[:n], xs[:n], wid[:n]
        elif seq[0] >= 3 and seq[0] >= 2 * max(seq[1:]):
            n = seq[0] - 1
            ys, xs, wid = ys[n:], xs[n:], wid[n:]
        else:
            break
    return ys, xs, wid


def segments(kind, side, ys, xs, wid):
    """One traced side as straight candidates: cut at jumps and turns, stems dropped."""
    out, a = [], 0
    cuts = pivots(xs) + [len(xs) - 1]
    for c in cuts:
        if c > a:
            for ys_, xs_ in split_jumps(ys[a:c + 1], xs[a:c + 1]):
                i = ys.index(ys_[0])
                out.append((kind, side) + strip_ends(ys_, xs_, wid[i:i + len(ys_)]))
        a = c
    return out


def outer_edges(bm):
    """Left and right silhouettes as edges: (kind, side, ys, xs, widths)."""
    runs = [row_runs(r) for r in bm]
    rows = [y for y, r in enumerate(runs) if r]
    out = []
    for side in ('L', 'R'):
        xs = [runs[y][0][0] if side == 'L' else runs[y][-1][1] for y in rows]
        wid = []
        for y in rows:
            r = runs[y][0] if side == 'L' else runs[y][-1]
            wid.append(r[1] - r[0] + 1 if len(runs[y]) > 1 else None)
        out += segments('outer', side, rows, xs, wid)
    return out


def inner_edges(bm):
    """Both sides of every run that is neither first nor last, chained down the rows."""
    runs = [row_runs(r) for r in bm]
    chains, open_ = [], {}
    for y, rr in enumerate(runs):
        mids = rr[1:-1]
        nxt = {}
        for r in mids:
            prev = [k for k in open_ if k[0] <= r[1] + 1 and r[0] <= k[1] + 1]
            sibs = [m for m in mids if prev and m[0] <= prev[0][1] + 1 and prev[0][0] <= m[1] + 1]
            if len(prev) == 1 and len(sibs) == 1:
                ch = open_[prev[0]]
                ch.append((y, r))
            else:
                ch = [(y, r)]
                chains.append(ch)
            nxt[r] = ch
        open_ = nxt
    out = []
    for ch in chains:
        ys = [y for y, _ in ch]
        for side, i in (('l', 0), ('r', 1)):
            out += segments('inner', side, ys, [r[i] for _, r in ch], [r[1] - r[0] + 1 for _, r in ch])
    return out


def strip(ys, xs):
    """Least band width over all slopes; under 1 means a digital straight line."""
    n = len(ys)
    y, x = np.array(ys, float), np.array(xs, float)
    slopes = {0.0}
    for i in range(n):
        for j in range(i + 1, n):
            slopes.add((x[j] - x[i]) / (y[j] - y[i]))
    best = None
    for s in slopes:
        d = x - s * y
        w = (d.max() - d.min()) / max(1.0, abs(s))    # across the minor axis: rows on a shallow edge
        if best is None or w < best:
            best = w
    return float(best)


def run_lengths(xs):
    """Run sequence of an edge: rows per column when it never moves more than a
    column a row, else the column steps."""
    steps = [b - a for a, b in zip(xs, xs[1:])]
    if any(abs(s) > 1 for s in steps):
        return [abs(s) for s in steps if s], 'steps'
    out, n = [], 1
    for s in steps:
        if s == 0:
            n += 1
        else:
            out.append(n)
            n = 1
    out.append(n)
    return out, 'rows'


def kinks(seq):
    """Runs 2+ longer or shorter than both neighbours."""
    return sum(1 for a, b, c in zip(seq, seq[1:], seq[2:]) if (b - a) * (b - c) > 0 and min(abs(b - a), abs(b - c)) >= 2)


def score_edge(e, width, k):
    kind, side, ys, xs, wid = e
    dx = xs[-1] - xs[0]
    if len(ys) < 4 or abs(dx) < 2:
        return None
    seq, unit = run_lengths(xs)
    steps = [b - a for a, b in zip(xs, xs[1:])]
    back = sum(1 for s in steps if s and (s > 0) != (dx > 0))
    w = strip(ys, xs)
    chord = [xs[0] + dx * (y - ys[0]) / (ys[-1] - ys[0]) for y in ys]
    bow = float(np.mean([a - b for a, b in zip(xs, chord)]))
    if side in ('R', 'r'):
        bow = -bow
    inner = seq[1:-1]
    return dict(kind=kind, side=side, rows=len(ys), dx=abs(dx), strip=w, straight=w < 1 - 1e-9, bow=bow, runs=seq, unit=unit,
                kinks=kinks(seq), uneven=len(inner) >= 2 and max(inner) - min(inner) >= 2, back=back,
                thin=sum(1 for v in wid if v is not None and v < k) if kind == 'outer' else 0,
                y0=ys[0], y1=ys[-1])


def score(bm, k):
    """Scores of every diagonal edge of a bitmap (cropped to its ink)."""
    bm = lib.crop(bm)
    out = []
    for e in outer_edges(bm) + inner_edges(bm):
        s = score_edge(e, bm.shape[1], k)
        if s:
            out.append(s)
    return out


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
    opt = ap.parse_args()
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
