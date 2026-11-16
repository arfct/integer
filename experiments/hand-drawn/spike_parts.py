"""Spike 2: derive the letters that share a part instead of rendering each alone.

    .venv/bin/python experiments/hand-drawn/spike_parts.py

Reads the committed drawings and writes nothing but a contact sheet and a
table. Rules, applied per grid and weight, with the stem-left letter as the
master of each family:

  d  = b mirrored (ink and sidebearings)
  q  = p mirrored
  p  = b's bowl flipped top to bottom, on p's own descender
  h  = n below the x-height, under h's own ascender
  u  = n turned half a turn
  accented letter = its base letter's drawing, with the accent rows of the
       accented drawing kept above it (below it for the cedilla)

The table says how many drawings each rule changes and by how many pixels:
the price in fidelity to the independent render, which is what an override
would have to buy back where a rule is wrong for a size.
"""
import collections
import os
import sys
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit  # noqa: E402
import lib  # noqa: E402


def glyph(bm, adv, left=0):
    return {'bm': bm, 'adv': adv, 'left': left, 'box': lib.ink_box(bm)}


def place(shape_rows, adv, ink, y0, lsb):
    """A fresh box with `ink` (cropped array) at row y0 and left bearing lsb."""
    bm = np.zeros((shape_rows, max(adv + 1, lsb + ink.shape[1] + 1)), dtype=bool)
    bm[y0:y0 + ink.shape[0], lsb:lsb + ink.shape[1]] = ink
    return bm


def reshaped(F, src, dst, turn=False):
    """src's ink mirrored (or turned half a turn), set at dst's own left bearing;
    the advance moves only by the change in ink width, so the count of pixels
    moved is a change of shape and never a shift."""
    g, d = F['G'][src], F['G'][dst]
    lsb, w, rsb = audit.bearing(F, dst)
    ink = lib.crop(g['bm'])[::-1, ::-1] if turn else lib.crop(g['bm'])[:, ::-1]
    adv = d['adv'] + ink.shape[1] - w
    y0 = F['xtop'] + F['base'] - 1 - int(g['box'][1]) if turn else int(g['box'][0])   # a half turn is about the x band's centre
    return glyph(place(g['bm'].shape[0], adv, ink, y0, max(lsb, 0)), adv)


def with_band(F, dst, band_ink, top, keep_above=True):
    """dst with its rows from `top` to the baseline replaced by band_ink, stems aligned at the ink's left."""
    g = F['G'][dst]
    lsb, w, rsb = audit.bearing(F, dst)
    old = g['bm']
    adv = g['adv'] + (band_ink.shape[1] - w)
    bm = np.zeros((old.shape[0], max(adv + 1, lsb + band_ink.shape[1] + 1)), dtype=bool)
    keep = old.copy()
    keep[top:F['base']] = False
    bm[:, :min(keep.shape[1], bm.shape[1])] = keep[:, :bm.shape[1]]
    bm[top:top + band_ink.shape[0], lsb:lsb + band_ink.shape[1]] = band_ink
    return glyph(bm, adv)


def derive(F):
    """{char: new glyph} for one size, and the rule that made each."""
    G, out, rule = F['G'], {}, {}
    xt, base = F['xtop'], F['base']
    out['d'] = reshaped(F, 'b', 'd'); rule['d'] = 'd = mirror b'
    bowl = audit.band(F, 'b', xt)[::-1]
    out['p'] = with_band(F, 'p', bowl, xt); rule['p'] = 'p = flip b'
    Fp = dict(F, G=dict(G, p=out['p']))
    out['q'] = reshaped(Fp, 'p', 'q'); rule['q'] = 'q = mirror p'
    out['h'] = with_band(F, 'h', audit.band(F, 'n', xt), xt); rule['h'] = 'h = n + ascender'
    out['u'] = reshaped(F, 'n', 'u', turn=True); rule['u'] = 'u = turn n'
    for cp in range(0xC0, 0x100):
        ch = chr(cp)
        nfd = unicodedata.normalize('NFD', ch)
        if len(nfd) != 2 or ch not in G or nfd[0] not in G or nfd[0] in 'ij':
            continue
        b = out.get(nfd[0], G[nfd[0]])
        a = G[ch]
        top = F['captop'] if nfd[0].isupper() else xt
        bot = base if nfd[1] == '\u0327' else a['bm'].shape[0]
        rows = max(a['bm'].shape[0], b['bm'].shape[0])
        bm = np.zeros((rows, max(b['bm'].shape[1], a['bm'].shape[1] + 4) + 4), dtype=bool)
        bm[:b['bm'].shape[0], :b['bm'].shape[1]] = b['bm']
        # the accent keeps its place over the base: shift it by the move of the base's centre
        old = lib.ink_box(a['bm'][top:bot])
        new = lib.ink_box(b['bm'][top:bot])
        acc = a['bm'].copy()
        acc[top:bot] = False
        if old is not None and new is not None and acc.any():
            shift = int(round(((new[2] + new[3]) - (old[2] + old[3])) / 2)) + (b['left'] - a['left'])
            ys, xs = np.where(acc)
            xs = xs + shift
            ok = (xs >= 0) & (xs < bm.shape[1])
            bm[ys[ok], xs[ok]] = True
        out[ch] = glyph(bm, b['adv'], b['left'])
        rule[ch] = 'accent on base'
    return out, rule


def diff(a, b):
    """Pixels that differ between two glyphs, placed by their left offsets."""
    h = max(a['bm'].shape[0], b['bm'].shape[0])
    lo = min(a['left'], b['left'])
    w = max(a['bm'].shape[1] + a['left'], b['bm'].shape[1] + b['left']) - lo
    A = np.zeros((h, w), dtype=bool)
    B = np.zeros((h, w), dtype=bool)
    A[:a['bm'].shape[0], a['left'] - lo:a['left'] - lo + a['bm'].shape[1]] = a['bm']
    B[:b['bm'].shape[0], b['left'] - lo:b['left'] - lo + b['bm'].shape[1]] = b['bm']
    return A, B


def line(F, text, repl=None):
    """A line of text as (bitmap, before-bitmap) on a common canvas."""
    h = max(g['bm'].shape[0] for g in F['G'].values())
    cells_new, cells_old = [], []
    for ch in text:
        if ch == ' ':
            cells_new.append(np.zeros((h, 3), dtype=bool)); cells_old.append(np.zeros((h, 3), dtype=bool))
            continue
        old = F['G'][ch]
        new = (repl or {}).get(ch, old)
        wd = max(old['adv'], new['adv']) + 1
        for g, cells in ((new, cells_new), (old, cells_old)):
            c = np.zeros((h, wd + 2), dtype=bool)
            ys, xs = np.where(g['bm'])
            xs = xs + g['left'] + 1
            ok = (xs >= 0) & (xs < c.shape[1])
            c[ys[ok], xs[ok]] = True
            cells.append(c)
    return np.hstack(cells_new), np.hstack(cells_old)


def trim(new, old):
    ys = np.where((new | old).any(axis=1))[0]
    return new[ys.min():ys.max() + 1], old[ys.min():ys.max() + 1]


def main():
    stats = collections.defaultdict(lambda: collections.Counter())
    pairs = collections.Counter()
    for g in lib.GRIDS:
        for w in lib.WEIGHTS:
            F = audit.integer_font(g, w)
            out, rule = derive(F)
            bandname = '7-12' if g <= 12 else '13-24' if g <= 24 else '25-48'
            for ch, new in out.items():
                A, B = diff(F['G'][ch], new)
                n = int((A ^ B).sum())
                for key in (rule[ch], rule[ch] + ' ' + bandname):
                    stats[key]['drawings'] += 1
                    stats[key]['changed'] += n > 0
                    stats[key]['pixels'] += n
                    stats[key]['ink'] += int(A.sum())
                    stats[key]['advance'] += new['adv'] != F['G'][ch]['adv']
            F2 = audit.finish(dict(F, G=dict(F['G'], **{c: dict(v) for c, v in out.items()})))
            R0, R2 = audit.audit_font(F)[0], audit.audit_font(F2)[0]
            for key in ('pairs differing', 'pairs', 'accented base differs', 'accented'):
                pairs['before ' + key] += R0[key]
                pairs['after ' + key] += R2[key]
            left = [k for k in R2 if k.startswith('pair ') and R2[k]]
            if left:
                print(f'  still differing at {g} {w}: ' + ', '.join(left))
    print('rule                      drawings  changed  pixels moved  share of ink  advance changed')
    for key in ('d = mirror b', 'p = flip b', 'q = mirror p', 'h = n + ascender', 'u = turn n', 'accent on base'):
        for suffix in ('', ' 7-12', ' 13-24', ' 25-48'):
            s = stats[key + suffix]
            print(f"{(key + suffix):<26}{s['drawings']:>8}{s['changed']:>9}{s['pixels']:>14}{100 * s['pixels'] / max(1, s['ink']):>13.1f}%{s['advance']:>17}")
    print(f"bowl/arch pairs differing: before {pairs['before pairs differing']}, after {pairs['after pairs differing']} of {pairs['before pairs']}")
    print(f"accented letters whose base differs: before {pairs['before accented base differs']}, after {pairs['after accented base differs']} of {pairs['before accented']}")

    rows = []
    text = 'bdpq nhu \u00e4\u00e2\u00e5 \u00fc\u00fb \u00e0\u00e9\u00f1 \u00c0\u00c4\u00c7'
    for g, w, scale in ((9, 'regular', 7), (12, 'regular', 6), (12, 'bold', 6), (16, 'regular', 5), (24, 'regular', 3), (32, 'regular', 3)):
        F = audit.integer_font(g, w)
        out, _ = derive(F)
        new, old = line(F, text, out)
        new, old = trim(new, old)
        rows.append([(f'{g} {w}: committed', lib.cell(old, scale))])
        rows.append([(f'{g} {w}: derived (green added, pink removed)', lib.cell(new, scale, before=old))])
    print(lib.sheet(rows, os.path.join(lib.IMG, 'spike-parts.png'), title='Spike 2: letters derived from shared parts'))


if __name__ == '__main__':
    main()
