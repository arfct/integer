"""Spike 3: a jaggy-normalizing pass, as a guarded local search over the audit's own counts.

    .venv/bin/python experiments/hand-drawn/spike_jaggies.py [--grids 20,24,32,40] [--weights regular,bold]

For each glyph with a staircase defect (a hard kink, a non-monotone arc on a
round glyph, uneven steps on a straight diagonal) the pass tries moves on the
pixels along the offending staircase only:

  flip   ink a clear pixel across the edge, or clear an ink pixel on it
  slide  move an edge pixel one step sideways (clear it, ink its neighbour)

and, for the letters the importer mirrors, the same move on the mirror image.
A move is kept when the defect score drops and nothing else gets worse: the
same pieces and counters, the same ink box, no new one-pixel bump or dent, no
new pixel without an orthogonal neighbour, no more pixels thinner than the
stroke (by the importer's own rule: k across a steep stroke, h down a shallow
one) and none in a spot thicker than the thickest stroke. Best move first, at most eight
moves per glyph.

It reads the committed drawings and writes a table and a contact sheet. It
has no access to the outline's coverage, so it cannot prefer the move that
is truer to the source; in the importer it would rank equal moves by coverage.
"""
import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit  # noqa: E402
import lib  # noqa: E402

MIRRORED = set(audit.SYM_LR)


def across(r):
    """The clear pixels on the far side of a run's edge."""
    x, y, dx, dy, n = r
    if dx == 1:
        return [(y - 1, x + i) for i in range(n)]
    if dx == -1:
        return [(y, x - 1 - i) for i in range(n)]
    if dy == 1:
        return [(y + i, x) for i in range(n)]
    return [(y - 1 - i, x - 1) for i in range(n)]


def defects(bm, ch):
    """(score, ink pixels and clear pixels along the defective staircases)."""
    score = 0
    ink, clear = set(), set()
    if ch in audit.INFLECTED:
        return 0, ink, clear
    sections, _ = audit.staircases(bm)
    for sec in sections:
        bad = 0
        hs = [r for r in sec if r[2]]
        vs = [r for r in sec if r[3]]
        for part in (hs, vs):
            lens = [r[4] for r in part]
            bad += 3 * len(audit.reversals(lens, True))
            if ch in audit.ROUND:
                bad += len(audit.reversals(lens, False))
        if ch in audit.DIAG:
            major = hs if sum(r[4] for r in hs) >= sum(r[4] for r in vs) else vs
            lens = [r[4] for r in major]
            if len(lens) >= 3 and max(lens) - min(lens) >= 2:
                bad += 1
        if bad:
            score += bad
            for r in sec:
                ink.update(audit.run_pixels(r))
                clear.update(across(r))
    return score, ink, clear


def run_lengths(bm):
    """Per ink pixel, the lengths of its horizontal and its vertical run."""
    def runs(a):
        out = np.zeros(a.shape, dtype=int)
        for y in range(a.shape[0]):
            x = 0
            while x < a.shape[1]:
                if a[y, x]:
                    j = x
                    while j < a.shape[1] and a[y, j]:
                        j += 1
                    out[y, x:j] = j - x
                    x = j
                else:
                    x += 1
        return out
    return runs(bm), runs(bm.T).T


def guards(bm, k, h):
    out_, in_, _ = audit.pimples(bm)
    rh, rv = run_lengths(bm)
    steep = rv >= rh                     # the importer's rule: a steep stroke is k across, a shallow one h down
    thin = bm & ((steep & (rh < k)) | (~steep & (rv < h)))
    thick = bm & (np.minimum(rh, rv) > max(k, h))
    return dict(top=audit.topology(bm), box=lib.ink_box(bm), bumps=out_ + in_, orphans=int(audit.orphans(bm).sum()),
                thin=int(thin.sum()), thick=int(thick.sum()))


def worse(g1, g0):
    return (g1['top'] != g0['top'] or g1['box'] != g0['box'] or g1['bumps'] > g0['bumps']
            or g1['orphans'] > g0['orphans'] or g1['thin'] > g0['thin'] or g1['thick'] > g0['thick'])


def normalize(bm, ch, k, h, max_moves=8):
    """The cleaned bitmap and the number of moves made."""
    bm = bm.copy()
    H, W = bm.shape
    box = lib.ink_box(bm)
    moves = 0

    def images(p):
        pts = {p}
        if ch in MIRRORED:
            pts.add((p[0], box[2] + box[3] - p[1]))
        return pts

    for _ in range(max_moves):
        s0, ink, clear = defects(bm, ch)
        if not s0:
            break
        g0 = guards(bm, k, h)
        cands = [((), (p,)) for p in clear] + [((p,), ()) for p in ink]
        for p in ink:
            for d in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                q = (p[0] + d[0], p[1] + d[1])
                if q in clear:
                    cands.append(((p,), (q,)))
        best = None
        for off, on in cands:
            off_ = set().union(*[images(p) for p in off]) if off else set()
            on_ = set().union(*[images(p) for p in on]) if on else set()
            if any(not (0 <= y < H and 0 <= x < W) for y, x in off_ | on_):
                continue
            t = bm.copy()
            for y, x in off_:
                t[y, x] = False
            for y, x in on_:
                t[y, x] = True
            s1 = defects(t, ch)[0]
            if s1 >= s0 or (best and (s1, len(off_ | on_)) >= best[:2]):
                continue
            if worse(guards(t, k, h), g0):
                continue
            best = (s1, len(off_ | on_), t)
        if best is None:
            break
        bm = best[2]
        moves += 1
    return bm, moves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', default='20,24,32,40')
    ap.add_argument('--weights', default='regular,bold')
    opt = ap.parse_args()
    grids = [int(g) for g in opt.grids.split(',')]
    T = collections.Counter()
    results = {}
    print('size            glyphs  defective  score before  after  cleared  moves  pixels changed')
    for g in grids:
        for w in opt.weights.split(','):
            F = audit.integer_font(g, w)
            c = collections.Counter()
            for ch in audit.ASCII:
                if ch not in F['G'] or F['G'][ch]['box'] is None:
                    continue
                bm = F['G'][ch]['bm']
                s0 = defects(bm, ch)[0]
                c['glyphs'] += 1
                if not s0:
                    continue
                new, moves = normalize(bm, ch, F['k'], F['h'])
                s1 = defects(new, ch)[0]
                c['defective'] += 1
                c['before'] += s0
                c['after'] += s1
                c['cleared'] += s1 == 0
                c['moves'] += moves
                c['pixels'] += int((new ^ bm).sum())
                results[(g, w, ch)] = (bm, new, s0, s1)
            T.update(c)
            print(f"{g:>2} {w:<10}{c['glyphs']:>9}{c['defective']:>11}{c['before']:>14}{c['after']:>7}{c['cleared']:>9}{c['moves']:>7}{c['pixels']:>16}")
    print(f"{'all':<13}{T['glyphs']:>9}{T['defective']:>11}{T['before']:>14}{T['after']:>7}{T['cleared']:>9}{T['moves']:>7}{T['pixels']:>16}")

    # sheet: the glyphs with the largest drop, and the ones the pass could not help
    def cellpair(key):
        bm, new, s0, s1 = results[key]
        b = lib.ink_box(bm | new)
        sl = (slice(b[0], b[1] + 1), slice(b[2], b[3] + 1))
        _, _, _, marks = audit.jaggies(bm, key[2])
        scale = 7 if key[0] <= 24 else 5
        lab = f'{key[2]} {key[0]} {key[1]}'
        return ((f'{lab}\nscore {s0}', lib.cell(bm[sl], scale, marks=marks[sl])),
                (f'{lab}\nscore {s1}', lib.cell(new[sl], scale, before=bm[sl])))

    helped = sorted((k for k, v in results.items() if v[3] < v[2] and k[0] <= 32),
                    key=lambda k: (k[0], -(results[k][2] - results[k][3])))
    stuck = sorted((k for k, v in results.items() if v[3] == v[2] and k[0] <= 32), key=lambda k: -results[k][2])[:6]
    rows = []
    per = collections.defaultdict(list)
    for k in helped:
        if len(per[k[0]]) < 6:
            per[k[0]].append(k)
    for g in grids:
        if per[g]:
            pairs = [cellpair(k) for k in per[g]]
            rows.append(f'{g}: committed above (red: the kinked run), after the pass below (green added, pink removed)')
            rows.append([p[0] for p in pairs])
            rows.append([p[1] for p in pairs])
    if stuck:
        pairs = [cellpair(k) for k in stuck]
        rows.append('no guarded move found: these stay as they are')
        rows.append([p[0] for p in pairs])
    print(lib.sheet(rows, os.path.join(lib.IMG, 'spike-jaggies.png'), title='Spike 3: guarded jaggy normalization'))


if __name__ == '__main__':
    main()
