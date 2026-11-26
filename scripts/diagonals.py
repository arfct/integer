"""Straight diagonals: fixed-step redraws of the letters built from straight strokes.

The erosion in import-inter.py tests one pixel at a time and cannot see a
slope, so the diagonals it leaves take uneven steps. After it, each letter
here is drawn again from its strokes: a line from one stroke end to the other
whose steps are as even as whole pixels allow, at a thickness that reads as
the instance's stem. A redraw replaces the eroded drawing only when it is one
piece, fills the same box, has the same counters, is no lighter, and is no
less straight by the measure below; otherwise the eroded drawing stays.

The first half is the straightness measure (experiments/straight-diagonals/
measure.py reports with it); the second half is the recipes.
"""
import math

import numpy as np


def crop(bm):
    ys, xs = np.where(bm)
    if not len(ys):
        return bm[:0, :0]
    return bm[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


# --- Straightness -------------------------------------------------------------
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
    bm = crop(bm)
    out = []
    for e in outer_edges(bm) + inner_edges(bm):
        s = score_edge(e, bm.shape[1], k)
        if s:
            out.append(s)
    return out


def bent(bm, k=1):
    """(edges that are not digital straight lines, kinks) of a drawing."""
    s = score(bm, k)
    return sum(1 for e in s if not e['straight']), sum(e['kinks'] for e in s)


# --- Drawing ------------------------------------------------------------------
def edge(y0, xa, y1, xb):
    """Pixels of an evenly stepped line from (y0, xa) to (y1, xb), y0 <= y1."""
    R, n = y1 - y0 + 1, abs(xb - xa) + 1
    sg = 1 if xb >= xa else -1
    if n <= R:
        return [(y0 + i, xa + sg * (((2 * i + 1) * n) // (2 * R))) for i in range(R)]
    return [(y0 + ((2 * j + 1) * R) // (2 * n), xa + sg * j) for j in range(n)]


def spread(R, n):
    """0 when n columns divide R rows exactly (every run the same), else 1."""
    return 0 if R % n == 0 or n % R == 0 else 1


CROSSING = 0.6    # pixels a crossing stroke may be thinner across than the stem


def fit(k, cols, R, give=0.0):
    """Row thickness of a diagonal that reads as a stem k wide.

    A stroke leaning s columns a row and t pixels wide along the row is
    t / sqrt(1 + s*s) thick across. `cols(t)` is the columns the stroke's
    edge crosses over R rows when it is t wide (a wider stroke in the same
    box leans less), so t is the whole number whose thickness across comes
    nearest k, the smaller on a tie, and never under k. With `give`, the
    thinnest t within that many pixels of k is taken instead: two strokes
    that cross add their ink at the crossing, and give it back here."""
    best = None
    for t in range(k, 3 * k + 1):
        n = cols(t)
        if n < 0:
            break
        s = n / max(1, R - 1)
        across = t / math.sqrt(1 + s * s)
        if give and across >= k - give:
            return t
        d = abs(across - k)
        if best is None or d < best[0] - 1e-9:
            best = (d, t)
    return best[1] if best else k


def stroke(bm, y0, xa, y1, xb, t):
    """Stamp a line whose left edge runs from column xa at row y0 to xb at y1,
    t wide along the row."""
    h, w = bm.shape
    R, n = y1 - y0 + 1, abs(xb - xa) + 1
    if n > R:
        t = max(1, t - (-(-n // R) - 1))      # shallow: the steps supply part of the row thickness
    for y, x in edge(y0, xa, y1, xb):
        if 0 <= y < h:
            bm[y, max(0, x):max(0, min(w, x + t))] = True


def narrowest(W, t):
    return t if (W - t) % 2 == 0 else t + 1


def pick_width(W, t, R, cols):
    """With the parity option: W, or W -+ 1 when W - t is odd, so an apex is
    exactly t wide; cols(W') gives the columns a leg crosses."""
    if (W - t) % 2 == 0:
        return W
    return min((W + 1, W - 1), key=lambda w: (spread(R, cols(w)), -w))


def mirror(bm):
    return bm | bm[:, ::-1]


def chevron(W, H, t, a):
    """Two legs meeting at the top centre, apex a wide, feet at the bottom corners."""
    bm = np.zeros((H, W), bool)
    x0 = (W - a) // 2
    stroke(bm, 0, x0, H - 1, 0, t)
    bm = mirror(bm)
    for y in range(H):                        # an apex wider than both legs: keep it closed
        r = row_runs(bm[y])
        if len(r) == 1 or y > 0:
            break
        bm[y, x0:W - x0] = True
    return bm


def draw_A(bm, hint, k, h, parity, up=True, bar=True):
    src = bm if up else bm[::-1]
    H, W = src.shape
    t = fit(k, lambda t: (W - t) / 2, H)
    if parity:
        W = pick_width(W, t, H, lambda w: (w - t) // 2 + 1)
        t = fit(k, lambda t: (W - t) / 2, H)
    a = narrowest(W, t)
    out = chevron(W, H, t, a)
    if bar:
        seen2 = False
        for y in range(H):
            n = len(row_runs(src[y]))
            seen2 = seen2 or n >= 2
            if seen2 and n == 1:
                r = row_runs(out[y])
                out[y, r[0][0]:r[-1][1] + 1] = True
    return out if up else out[::-1]


def draw_V(bm, hint, k, h, parity):
    return draw_A(bm, hint, k, h, parity, up=False, bar=False)


def open_rows(bm):
    """Rows where three or more strokes stand apart: how deep the counters of
    a W or an M run."""
    return sum(1 for y in range(bm.shape[0]) if len(row_runs(bm[y])) >= 3)


def roomy(src, out):
    """The strokes of a W or an M stand apart over half the height, or over
    as many rows as in the eroded drawing if that is fewer."""
    return open_rows(out) >= min(open_rows(src), -(-src.shape[0] // 2))


def draw_W(bm, hint, k, h, parity):
    """Four strokes: the outer two from the top corners, the inner two from
    the middle apex, meeting in two feet. When the letter has no room for
    four strokes of the full thickness, the inner two give way first, then
    all four."""
    H, W0 = bm.shape
    bot = row_runs(hint[H - 1])
    if len(bot) != 2:
        bot = row_runs(bm[H - 1])
    if len(bot) != 2:
        return None
    c = (W0 - 1) // 2
    ymid = next((y for y in range(H) if bm[y, c] or bm[y, W0 - 1 - c]), None)
    if ymid is None or ymid > H - 3:
        return None
    t0 = fit(k, lambda t: (bot[0][0] + bot[0][1] + 1 - t) / 2, H)
    pairs = [(t0, t0)] + [(t0, ti) for ti in range(t0 - 1, 0, -1)] + [(t, t) for t in range(t0 - 1, 0, -1)]
    for t, ti in pairs:
        if parity and ti < t0:                # a changed width must not cost the W its weight
            return None
        W = W0
        b0, b1 = bot[0]
        # The foot is as wide as the hinted render left it, between the
        # thicker stroke and both strokes side by side.
        vw = max(t, min(b1 - b0 + 1, t + ti))
        if parity:
            vw = t
        b0 = (b0 + b1 + 1 - vw) // 2
        b1 = b0 + vw - 1
        if parity:
            W = pick_width(W, ti, H - ymid, lambda w: (w - ti) // 2 - (b1 - ti + 1) + 1)
        m = narrowest(W, ti)
        m0 = (W - m) // 2
        if b1 - ti + 1 > m0 or b0 < 0:
            continue
        out = np.zeros((H, W), bool)
        stroke(out, 0, 0, H - 1, b0, t)
        for y, x in edge(ymid, m0, H - 1, b1 - ti + 1):
            out[y, x:x + ti] = True
        out[H - 1, b0:b1 + 1] = True
        out = mirror(out)
        if accept(bm, out) and roomy(bm, out):
            return out
    return None


def draw_X(bm, hint, k, h, parity):
    H, W = bm.shape
    t = fit(k, lambda t: W - t, H, give=CROSSING)
    if W - t < 1:
        return None
    out = np.zeros((H, W), bool)
    stroke(out, 0, 0, H - 1, W - t, t)
    return mirror(out)


def draw_Y(bm, hint, k, h, parity):
    H, W = bm.shape
    bot = row_runs(bm[H - 1])
    if len(bot) != 1:
        return None
    s0, s1 = bot[0]
    yj = H - 1
    while yj > 0 and row_runs(bm[yj - 1]) == bot:
        yj -= 1
    if yj < 2:
        return None
    t = fit(k, lambda t: max(0, s0 - 1), yj)
    out = np.zeros((H, W), bool)
    stroke(out, 0, 0, yj - 1, max(0, s0 - 1), t)
    out = mirror(out)
    out[yj:, s0:s1 + 1] = True
    r = row_runs(out[yj - 1])
    out[yj - 1, r[0][0]:r[-1][1] + 1] = True
    if len(row_runs(out[0])) != 2:            # the arms have closed: no Y
        return None
    return out


def draw_y(bm, hint, k, h, parity):
    """The long stroke runs from the top right to the hook in one line; the
    short arm ends against it."""
    H, W = bm.shape
    first1 = next((y for y in range(H) if len(row_runs(bm[y])) == 1), None)
    if first1 is None or first1 < 2:
        return None
    hook = H
    for y in range(first1 + 1, H):
        r, p = row_runs(bm[y]), row_runs(bm[y - 1])
        if len(r) != 1 or r[0][1] - r[0][0] + 1 > 2 * k + 1 or r[0][0] < p[0][0] - 1:
            hook = y
            break
    best = None
    # The hook is the eroded drawing's; the long stroke may end on any of the
    # rows over it, whichever leaves the straightest letter.
    for yt in range(hook - 1, max(first1, hook - 4), -1):
        L = row_runs(bm[yt])[0][0]
        t = fit(k, lambda t: W - t - L, yt + 1)
        if W - t < L:
            continue
        out = np.zeros((H, W), bool)
        out[yt + 1:] = bm[yt + 1:]
        line = edge(0, W - t, yt, L)
        xs = {}
        for y, x in line:
            out[y, x:x + t] = True
            xs[y] = min(x, xs.get(y, x))
        yj = min(first1, yt)
        tl = fit(k, lambda t: max(0, xs[yj - 1] - t), yj)
        stroke(out, 0, 0, yj - 1, max(0, xs[yj - 1] - tl), tl)      # the arm ends against the long stroke
        b = bent(out, k)
        if best is None or b < best[0]:
            best = (b, out)
    return best[1] if best else None


def draw_K(bm, hint, k, h, parity):
    """Stem, an arm from the top right corner down to the stem, and a leg from
    the arm to the bottom right corner. The arm meets the stem on any row
    from the waist down, and the leg leaves the arm on any row from there to
    the waist; the straightest pair wins."""
    H, W = bm.shape
    bot = row_runs(bm[H - 1])
    if len(bot) != 2:
        return None
    s = bot[0][1] + 1
    top = next((y for y in range(H) if len(row_runs(bm[y])) >= 2), None)
    if top is None or s >= W - 1:
        return None
    best = None
    for yj in range(max(top + 1, H // 3), H - 1):
        ta = fit(k, lambda t: W - t - s, yj - top + 1)
        if W - ta <= s:
            continue
        arm = edge(top, W - ta, yj, s)
        ax = {}
        for y, x in arm:
            ax[y] = max(x, ax.get(y, x))
        for yl in range(max(top + 1, yj - max(2, H // 3)), yj + 1):
            start = ax[yl]
            tl = fit(k, lambda t: W - t - start, H - yl)
            if W - tl < start:
                continue
            out = np.zeros((H, W), bool)
            out[:, :s] = True
            for y, x in arm:
                out[y, x:min(W, x + ta)] = True
            for y, x in edge(yl, start, H - 1, W - tl):
                out[y, x:min(W, x + tl)] = True
            if not accept(bm, out):
                continue
            key = (bent(out, k), int((out ^ bm).sum()))
            if best is None or key < best[0]:
                best = (key, out)
    return best[1] if best else None


def draw_M(bm, hint, k, h, parity):
    H, W = bm.shape
    bot = row_runs(bm[H - 1])
    s = bot[0][1] + 1
    c = (W - 1) // 2
    ys = [y for y in range(H) if bm[y, c]]
    if not ys or len(row_runs(bm[0])) < 2:
        return None
    yv = ys[-1]
    vr = [r for r in row_runs(bm[yv]) if r[0] <= c <= r[1]][0]
    e = row_runs(bm[0])[0][1]
    vw = vr[1] - vr[0] + 1
    best = None
    for tm in range(k, 0, -1):                # the diagonals give way when the letter has no room for them
        v = vw
        if parity or v < tm:
            v = narrowest(W, tm)
        v0 = (W - v) // 2
        a = max(0, e - tm + 1)
        if v0 < a or yv < 2:
            continue
        out = np.zeros((H, W), bool)
        out[:, :s] = True
        stroke(out, 0, a, yv, v0, tm)
        out = mirror(out)
        out[yv, v0:W - v0] = True
        if accept(bm, out) and roomy(bm, out):
            return out
    return None


def draw_N(bm, hint, k, h, parity):
    H, W = bm.shape
    top, bot = row_runs(bm[0]), row_runs(bm[H - 1])
    if len(top) < 2 or len(bot) < 2:
        return None
    s = bot[0][1] + 1
    e0, f0 = top[0][1], bot[-1][0]
    best = None
    for t in range(fit(k, lambda t: f0 - e0, H), 0, -1):
        a, b = max(0, e0 - t + 1), min(f0, W - t)
        if b <= a:
            continue
        out = np.zeros((H, W), bool)
        out[:, :s] = True
        out[:, W - s:] = True
        stroke(out, 0, a, H - 1, b, t)
        if accept(bm, out):
            return out
        best = best if best is not None else out
    return best


def draw_Z(bm, hint, k, h, parity, bottom=True):
    """The bars are the eroded drawing's; the diagonal runs corner to corner
    through them: the line is laid from the bar row above to the bar row
    below (or the foot) and only the rows between are stamped, so the
    silhouette stays straight into the bars."""
    H, W = bm.shape

    def full(y):
        r = row_runs(bm[y])
        return len(r) == 1 and r[0][1] - r[0][0] + 1 >= W - 1
    r0 = 0
    while r0 < H and full(r0):
        r0 += 1
    r1 = H - 1
    if bottom:
        while r1 > r0 and full(r1):
            r1 -= 1
    if r0 == 0 or r1 - r0 < 2:
        return None
    if any(len(row_runs(bm[y])) != 1 for y in range(r0, r1 + 1)):
        return None
    hi = row_runs(bm[r0 - 1])[0][1]
    xb = row_runs(bm[r1 + 1])[0][0] if bottom else row_runs(bm[r1])[0][0]
    y1 = r1 + 1 if bottom else r1
    best = None
    t0 = fit(k, lambda t: hi - t + 1 - xb, y1 - r0 + 2)
    for t in (t0, t0 + 1, t0 - 1):
        xa = hi - t + 1
        if t < 1 or xa < xb:
            continue
        out = bm.copy()
        out[r0:r1 + 1] = False
        R, n = y1 - r0 + 2, xa - xb + 1
        tt = max(1, t - (-(-n // R) - 1)) if n > R else t
        for y, x in edge(r0 - 1, xa, y1, xb):
            if r0 <= y <= r1:
                out[y, max(0, x):x + tt] = True
        if not accept(bm, out):
            continue
        key = (bent(out, k), abs(t - t0))
        if best is None or key < best[0]:
            best = (key, out)
    return best[1] if best else None


def draw_seven(bm, hint, k, h, parity):
    return draw_Z(bm, hint, k, h, parity, bottom=False)


def draw_slash(bm, hint, k, h, parity):
    H, W = bm.shape
    t = fit(k, lambda t: W - t, H)
    if W - t < 1:
        return None
    out = np.zeros((H, W), bool)
    stroke(out, 0, W - t, H - 1, 0, t)
    return out


def draw_backslash(bm, hint, k, h, parity):
    out = draw_slash(bm[:, ::-1], hint[:, ::-1], k, h, parity)
    return None if out is None else out[:, ::-1]


RECIPES = {
    'A': draw_A, 'V': draw_V, 'v': draw_V, 'W': draw_W, 'w': draw_W, 'X': draw_X, 'x': draw_X,
    'Y': draw_Y, 'y': draw_y, 'K': draw_K, 'k': draw_K, 'M': draw_M, 'N': draw_N,
    'Z': draw_Z, 'z': draw_Z, 'seven': draw_seven,
    'slash': draw_slash, 'backslash': draw_backslash,
}
# Letters whose width the parity option may change by a pixel, so that an
# apex or a vertex is exactly one stroke wide.
PARITY = {'avv': {'A', 'V', 'v'}, 'all': {'A', 'V', 'v', 'W', 'w', 'M'}}


def pieces(bm):
    seen = np.zeros(bm.shape, bool)
    n = 0
    h, w = bm.shape
    for y0 in range(h):
        for x0 in range(w):
            if bm[y0, x0] and not seen[y0, x0]:
                n += 1
                stack = [(y0, x0)]
                seen[y0, x0] = True
                while stack:
                    y, x = stack.pop()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            yy, xx = y + dy, x + dx
                            if 0 <= yy < h and 0 <= xx < w and bm[yy, xx] and not seen[yy, xx]:
                                seen[yy, xx] = True
                                stack.append((yy, xx))
    return n


def counters(bm):
    """Background regions, 4-connected, the outside counted once."""
    h, w = bm.shape
    pad = np.zeros((h + 2, w + 2), bool)
    pad[1:-1, 1:-1] = bm
    seen = pad.copy()
    n = 0
    for y0 in range(h + 2):
        for x0 in range(w + 2):
            if not seen[y0, x0]:
                n += 1
                stack = [(y0, x0)]
                seen[y0, x0] = True
                while stack:
                    y, x = stack.pop()
                    for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= yy < h + 2 and 0 <= xx < w + 2 and not seen[yy, xx]:
                            seen[yy, xx] = True
                            stack.append((yy, xx))
    return n


def gaps(bm):
    """White stretches between strokes, summed over the rows."""
    return sum(len(row_runs(bm[y])) - 1 for y in range(bm.shape[0]))


def accept(src, out):
    """A redraw is a letter: one piece, filling its box, with the counters
    of the eroded drawing, not lighter than it by more than a tenth, and
    with its strokes apart on at least half the rows they were."""
    return (out is not None and out.size and pieces(out) == 1
            and out[0].any() and out[-1].any() and out[:, 0].any() and out[:, -1].any()
            and counters(out) == counters(src) and out.sum() >= 0.9 * src.sum()
            and 2 * gaps(out) >= gaps(src))


def redraw(name, bm, hint, k, h, parity='off'):
    """(drawing, status) for a cropped eroded drawing `bm` and the hinted
    render `hint` in the same box. Status is 'redrawn', 'same', or 'kept'
    when no redraw passed. k and h are the instance's stem and bar."""
    rec = RECIPES.get(name)
    if rec is None or bm.size == 0:
        return bm, 'same'
    was = bent(bm, k)
    for par in ((True, False) if name in PARITY.get(parity, ()) else (False,)):
        try:
            out = rec(bm, hint, k, h, par)
        except (IndexError, ValueError, StopIteration, KeyError):
            out = None
        if out is None or not accept(bm, out):
            continue
        now = bent(out, k)
        if now[0] > was[0] or (now[0] == was[0] and now[1] > was[1]):
            continue
        if out.shape == bm.shape and (out == bm).all():
            return bm, 'same'
        return out, 'redrawn'
    return bm, 'kept'
