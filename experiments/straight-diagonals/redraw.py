"""Redraw the straight strokes of a committed drawing as digital straight lines.

Nothing here reads the outline. Each letter has a recipe that takes its
anchors from the committed drawing (ink box, stem, where the strokes start
and end, the bar rows) and draws every straight diagonal again with

  edge()    one column position per row, the columns spread evenly over the
            rows (Euclidean distribution, centred): runs differ by at most 1,
            full runs at both ends, a digital straight line by construction
  brush     a constant horizontal thickness t on every row, t being the
            median thickness of that stroke in the committed drawing

Two modes:

  fixed     the ink box is kept. An apex is the narrowest the box's parity
            allows: t wide when width - t is even, t + 1 wide when it is odd.
  parity    as fixed, but a letter with an apex on its centre line (A V v W w)
            whose width - t is odd is made 1 px wider or narrower, whichever
            gives the more even runs, so the apex is exactly t wide. W and w
            also get bottom vertices t wide, and M a vertex as narrow as its
            width allows.

redraw() returns the original bitmap when a recipe does not apply or the
result is not one connected piece.
"""
import statistics

import numpy as np

LETTERS = 'AVvWwXxYyKkMNZz7'


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


def stroke(bm, y0, xa, y1, xb, t):
    """Stamp a line whose left edge runs from column xa at row y0 to xb at y1."""
    h, w = bm.shape
    R, n = y1 - y0 + 1, abs(xb - xa) + 1
    if n > R:
        t = max(1, t - (-(-n // R) - 1))      # shallow: the steps supply part of the row thickness
    for y, x in edge(y0, xa, y1, xb):
        if 0 <= y < h:
            bm[y, max(0, x):max(0, min(w, x + t))] = True


def med(vals, default):
    return int(statistics.median_low(vals)) if vals else default


def thickness(bm, count, index, default, rows=None):
    """Median length of run `index` over the rows that have `count` runs."""
    vals = []
    for y in (rows if rows is not None else range(bm.shape[0])):
        r = runs(bm[y])
        if len(r) == count:
            vals.append(r[index][1] - r[index][0] + 1)
    return med(vals, default)


def narrowest(W, t):
    return t if (W - t) % 2 == 0 else t + 1


def pick_width(W, t, R, cols):
    """parity mode: W, or W -+ 1 when W - t is odd; cols(W') gives the columns a leg crosses."""
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
        r = runs(bm[y])
        if len(r) == 1 or y > 0:
            break
        bm[y, x0:W - x0] = True
    return bm


def draw_A(bm, k, mode, up=True, bar=True):
    src = bm if up else bm[::-1]
    H, W = src.shape
    t = thickness(src, 2, 0, k)
    if mode == 'parity':
        W = pick_width(W, t, H, lambda w: (w - t) // 2 + 1)
    a = narrowest(W, t)
    out = chevron(W, H, t, a)
    if bar:
        seen2 = False
        for y in range(H):
            n = len(runs(src[y]))
            seen2 = seen2 or n >= 2
            if seen2 and n == 1:
                r = runs(out[y])
                out[y, r[0][0]:r[-1][1] + 1] = True
    return out if up else out[::-1]


def draw_W(bm, k, mode):
    H, W = bm.shape
    bot = runs(bm[H - 1])
    if len(bot) != 2:
        return bm
    b0, b1 = bot[0]
    t = thickness(bm, 4, 0, thickness(bm, 2, 0, k))
    c = (W - 1) // 2
    ymid = next((y for y in range(H) if bm[y, c] or bm[y, W - 1 - c]), None)
    if ymid is None or ymid > H - 3:
        return bm
    if mode == 'parity':
        vw = t
        b0 = (b0 + b1 + 1 - vw) // 2
        b1 = b0 + vw - 1
        W2 = pick_width(W, t, H - ymid, lambda w: (w - t) // 2 - (b1 - t + 1) + 1)
        W = W2
    if b1 - b0 + 1 < t:
        b1 = b0 + t - 1
    m = narrowest(W, t)
    m0 = (W - m) // 2
    if b1 - t + 1 > m0:
        return bm
    out = np.zeros((H, W), bool)
    stroke(out, 0, 0, H - 1, b0, t)
    for y, x in edge(ymid, m0, H - 1, b1 - t + 1):
        out[y, x:x + t] = True
    out[H - 1, b0:b1 + 1] = True
    return mirror(out)


def draw_X(bm, k, mode):
    H, W = bm.shape
    t = thickness(bm, 2, 0, k)
    if W - t < 1:
        return bm
    out = np.zeros((H, W), bool)
    stroke(out, 0, 0, H - 1, W - t, t)
    return mirror(out)


def draw_Y(bm, k, mode):
    H, W = bm.shape
    bot = runs(bm[H - 1])
    if len(bot) != 1:
        return bm
    s0, s1 = bot[0]
    yj = H - 1
    while yj > 0 and runs(bm[yj - 1]) == bot:
        yj -= 1
    if yj < 2:
        return bm
    t = thickness(bm, 2, 0, k)
    out = np.zeros((H, W), bool)
    stroke(out, 0, 0, yj - 1, max(0, s0 - 1), t)
    out = mirror(out)
    out[yj:, s0:s1 + 1] = True
    r = runs(out[yj - 1])
    out[yj - 1, r[0][0]:r[-1][1] + 1] = True
    return out


def draw_y(bm, k, mode):
    H, W = bm.shape
    first1 = next((y for y in range(H) if len(runs(bm[y])) == 1), None)
    if first1 is None or first1 < 2:
        return bm
    t = thickness(bm, 2, 1, k)
    tl = thickness(bm, 2, 0, k)
    hook = H
    for y in range(first1 + 1, H):
        r, p = runs(bm[y]), runs(bm[y - 1])
        if len(r) != 1 or r[0][1] - r[0][0] + 1 > t + 1 or r[0][0] < p[0][0] - 1:
            hook = y
            break
    yt = hook - 1
    L = runs(bm[yt])[0][0]
    out = np.zeros((H, W), bool)
    out[hook:] = bm[hook:]
    line = edge(0, W - t, yt, L)
    for y, x in line:
        out[y, x:x + t] = True
    xs = {}
    for y, x in line:
        xs[y] = min(x, xs.get(y, x))
    yj = first1
    stroke(out, 0, 0, yj - 1, max(0, xs[yj - 1] - tl), tl)      # the arm ends against the long stroke
    return out


def draw_K(bm, k, mode):
    H, W = bm.shape
    bot = runs(bm[H - 1])
    if len(bot) != 2:
        return bm
    s = bot[0][1] + 1
    l0 = bot[1][0]
    top = next((y for y in range(H) if len(runs(bm[y])) >= 2), None)
    if top is None:
        return bm
    u0 = runs(bm[top])[-1][0]
    t = thickness(bm, 2, 1, k)
    R = [runs(bm[y])[-1][1] for y in range(H)]
    yw = min(range(top, H), key=lambda y: (R[y], y))
    if yw <= top or yw >= H - 1:
        return bm
    Ls = runs(bm[yw])[-1][0] if len(runs(bm[yw])) >= 2 else s
    Ls = max(Ls, s)
    if u0 <= Ls:
        return bm
    yj = min(H - 1, yw + round((Ls - s) * (yw - top) / (u0 - Ls)))
    out = np.zeros((H, W), bool)
    out[:, :s] = True
    arm = edge(top, u0, yj, s)
    for y, x in arm:
        out[y, x:min(W, x + t)] = True
    ax = {}
    for y, x in arm:
        ax[y] = max(x, ax.get(y, x))
    if yw + 1 > H - 1:
        return bm
    start = min(ax[yw], l0)
    for y, x in edge(yw + 1, start, H - 1, l0):
        out[y, x:min(W, x + t)] = True
    return out


def draw_M(bm, k, mode):
    H, W = bm.shape
    bot = runs(bm[H - 1])
    s = bot[0][1] + 1
    c = (W - 1) // 2
    ys = [y for y in range(H) if bm[y, c]]
    if not ys or len(runs(bm[0])) < 2:
        return bm
    yv = ys[-1]
    vr = [r for r in runs(bm[yv]) if r[0] <= c <= r[1]][0]
    e = runs(bm[0])[0][1]
    tm = min(k, thickness(bm, 4, 1, 1))
    vw = vr[1] - vr[0] + 1
    if mode == 'parity' or vw < tm:
        vw = narrowest(W, tm)
    v0 = (W - vw) // 2
    a = max(0, e - tm + 1)
    if v0 < a or yv < 2:
        return bm
    out = np.zeros((H, W), bool)
    out[:, :s] = True
    stroke(out, 0, a, yv, v0, tm)
    out = mirror(out)
    out[yv, v0:W - v0] = True
    return out


def draw_N(bm, k, mode):
    H, W = bm.shape
    top, bot = runs(bm[0]), runs(bm[H - 1])
    if len(top) < 2 or len(bot) < 2:
        return bm
    s = bot[0][1] + 1
    e0, f0 = top[0][1], bot[-1][0]
    t = thickness(bm, 3, 1, k)
    a, b = max(0, e0 - t + 1), min(f0, W - t)
    if b <= a:
        return bm
    out = np.zeros((H, W), bool)
    out[:, :s] = True
    out[:, W - s:] = True
    stroke(out, 0, a, H - 1, b, t)
    return out


def draw_Z(bm, k, mode, bottom=True):
    H, W = bm.shape

    def full(y):
        r = runs(bm[y])
        return len(r) == 1 and r[0][1] - r[0][0] + 1 >= W - 1
    r0 = 0
    while r0 < H and full(r0):
        r0 += 1
    r1 = H - 1
    if bottom:
        while r1 > r0 and full(r1):
            r1 -= 1
    if r0 == 0 or r1 - r0 < 2:
        return bm
    rows = range(r0, r1 + 1)
    if any(len(runs(bm[y])) != 1 for y in rows):
        return bm
    t = med([runs(bm[y])[0][1] - runs(bm[y])[0][0] + 1 for y in rows], k)
    # The diagonal runs corner to corner through the bars: the line is laid
    # from the bar row above to the bar row below (or the foot) and only the
    # rows between are stamped, so the silhouette stays straight into the bar.
    xa = runs(bm[r0 - 1])[0][1] - t + 1
    xb = runs(bm[r1 + 1])[0][0] if bottom else runs(bm[r1])[0][0]
    y1 = r1 + 1 if bottom else r1
    if xa < xb:
        return bm
    out = bm.copy()
    out[r0:r1 + 1] = False
    for y, x in edge(r0 - 1, xa, y1, xb):
        if r0 <= y <= r1:
            out[y, max(0, x):x + t] = True
    return out


RECIPES = {
    'A': lambda bm, k, m: draw_A(bm, k, m),
    'V': lambda bm, k, m: draw_A(bm, k, m, up=False, bar=False),
    'v': lambda bm, k, m: draw_A(bm, k, m, up=False, bar=False),
    'W': draw_W, 'w': draw_W, 'X': draw_X, 'x': draw_X, 'Y': draw_Y, 'y': draw_y,
    'K': draw_K, 'k': draw_K, 'M': draw_M, 'N': draw_N,
    'Z': draw_Z, 'z': draw_Z, '7': lambda bm, k, m: draw_Z(bm, k, m, bottom=False),
}


def redraw(ch, bm, k, mode='fixed'):
    """(new cropped bitmap, status) for a cropped drawing; status is 'redrawn',
    'same', or 'kept' when the recipe gave up or broke the letter."""
    if ch not in RECIPES or bm.size == 0:
        return bm, 'same'
    try:
        out = RECIPES[ch](bm, k, mode)
    except (IndexError, ValueError, StopIteration):
        return bm, 'kept'
    if out is bm:
        return bm, 'kept'
    if pieces(out) != 1 or not out[0].any() or not out[-1].any() or not out[:, 0].any() or not out[:, -1].any():
        return bm, 'kept'
    if out.shape == bm.shape and (out == bm).all():
        return bm, 'same'
    return out, 'redrawn'
