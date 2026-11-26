"""Run both redraw modes over the committed drawings and report.

    .venv/bin/python experiments/straight-diagonals/proto.py

Reads glyphs/<grid>/<weight>.txt, writes nothing there. Output:
  proto.txt                      the numbers (also printed)
  img/sheet-<mode>-<weight>.png  before / after, magnified, pixel grid; green
                                 pixels were added, pink ones removed
  img/apex.png                   A V v W M before / fixed / parity, every grid
  img/proof.png                  a line of text at 1x and 4x, before and after
  out/<mode>/<grid>-<weight>.txt the prototype bitmaps as text
"""
import collections
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib          # noqa: E402
import measure      # noqa: E402
import redraw       # noqa: E402

LETTERS = redraw.LETTERS + 'n'
MODES = ('fixed', 'parity')
TEXT = 'AVAVA vavav WAVY wavy MIXTAPE KNOX'
OUT = os.path.join(HERE, 'out')


def scale_for(grid):
    return 8 if grid <= 13 else 6 if grid <= 24 else 4 if grid <= 32 else 3


def align(a, b):
    """Two cropped bitmaps on one canvas, centred on each other's width."""
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])

    def put(m):
        c = np.zeros((h, w), bool)
        x = (w - m.shape[1]) // 2
        c[:m.shape[0], x:x + m.shape[1]] = m
        return c
    return put(a), put(b)


def constant(scores):
    """Edges whose runs are all one length, end runs allowed shorter."""
    n = 0
    for s in scores:
        inner = s['runs'][1:-1] if len(s['runs']) > 2 else s['runs']
        n += len(set(inner)) == 1 and max(s['runs']) == inner[0]
    return n


def main():
    lines = []

    def say(s=''):
        print(s)
        lines.append(s)

    new = {m: {} for m in MODES}
    tot = {m: collections.defaultdict(collections.Counter) for m in ('before',) + MODES}
    stat = {m: collections.Counter() for m in MODES}
    per_letter = {m: collections.defaultdict(collections.Counter) for m in ('before',) + MODES}
    widths = {m: [] for m in MODES}
    kept = {m: [] for m in MODES}
    apex = {m: collections.Counter() for m in ('before',) + MODES}
    for g in lib.GRIDS:
        for w in lib.WEIGHTS:
            meta, G = lib.load(g, w)
            k = meta['stem']
            for ch in LETTERS:
                src = lib.crop(G[ch]['bm'])
                sc = measure.score(src, k)
                t = measure.tally(sc)
                t['constant'] = constant(sc)
                t['drawings'] = 1
                t['bent drawings'] = t['bent'] > 0
                tot['before'][w].update(t)
                per_letter['before'][ch].update(t)
                if ch in 'AVv':
                    row = src[0] if ch == 'A' else src[-1]
                    apex['before'][(w, int(row.sum()) - k)] += 1
                for m in MODES:
                    out, status = redraw.redraw(ch, src, k, m)
                    new[m][(g, w, ch)] = out
                    stat[m][status] += 1
                    if status == 'kept':
                        kept[m].append(f'{ch} {g} {w}')
                    sc2 = measure.score(out, k)
                    t2 = measure.tally(sc2)
                    t2['constant'] = constant(sc2)
                    t2['drawings'] = 1
                    t2['bent drawings'] = t2['bent'] > 0
                    a, b = align(src, out)
                    t2['pixels'] = int((a ^ b).sum())
                    t2['ink before'] = int(src.sum())
                    t2['ink after'] = int(out.sum())
                    tot[m][w].update(t2)
                    per_letter[m][ch].update(t2)
                    if out.shape[1] != src.shape[1]:
                        widths[m].append(f'{ch} {g} {w} {src.shape[1]}>{out.shape[1]}')
                    if ch in 'AVv':
                        row = out[0] if ch == 'A' else out[-1]
                        apex[m][(w, int(row.sum()) - k)] += 1

    say(f'Redraw prototypes on {LETTERS} at grids {",".join(map(str, lib.GRIDS))}, three weights: {len(LETTERS) * len(lib.GRIDS) * 3} drawings')
    say('constant = edges whose interior runs are all one length; pixels = pixels that differ from the committed drawing')
    say()
    head = measure.HEAD + f"{'const':>7}{'pixels':>8}   drawings with a bent edge"
    for label in ('before',) + MODES:
        say(label)
        say(head)
        allc = collections.Counter()
        for w in lib.WEIGHTS:
            c = tot[label][w]
            allc.update(c)
            say(measure.line(w, c) + f"{c['constant']:>7}{c['pixels']:>8}   {c['bent drawings']} of {c['drawings']}")
        say(measure.line('all', allc) + f"{allc['constant']:>7}{allc['pixels']:>8}   {allc['bent drawings']} of {allc['drawings']}")
        if label != 'before':
            say(f"  redrawn {stat[label]['redrawn']}, identical to the committed drawing {stat[label]['same']}, recipe gave up {stat[label]['kept']}")
            say(f"  ink pixels {allc['ink before']} before, {allc['ink after']} after")
            say(f"  width changed in {len(widths[label])} drawings" + (': ' + ', '.join(widths[label]) if widths[label] else ''))
            say(f"  gave up on: {', '.join(kept[label]) if kept[label] else 'none'}")
        say()
    say('By letter: bent edges / edges, kinks, pixels changed')
    say(f"{'':<4}{'before':>16}{'fixed':>24}{'parity':>24}")
    for ch in LETTERS:
        cells = []
        for label in ('before',) + MODES:
            c = per_letter[label][ch]
            cells.append(f"{c['bent']:>3}/{c['edges']:<3} k{c['kinks']:<3}" + (f" px{c['pixels']:<5}" if label != 'before' else ''))
        say(f'{ch:<4}' + '   '.join(f'{x:>20}' for x in cells))
    say()
    say('Apex of A and vertex of V, v: ink in the end row minus the stem (0 = exactly one stem wide), drawings per weight')
    for label in ('before',) + MODES:
        for w in lib.WEIGHTS:
            d = {e: n for (ww, e), n in apex[label].items() if ww == w}
            say(f"  {label:<7} {w:<8} " + '  '.join(f'+{e}: {d[e]}' if e >= 0 else f'{e}: {d[e]}' for e in sorted(d)))
    open(os.path.join(HERE, 'proto.txt'), 'w').write('\n'.join(lines) + '\n')

    # --- the bitmaps as text --------------------------------------------------
    for m in MODES:
        os.makedirs(os.path.join(OUT, m), exist_ok=True)
        for g in lib.GRIDS:
            for w in lib.WEIGHTS:
                with open(os.path.join(OUT, m, f'{g}-{w}.txt'), 'w') as f:
                    for ch in LETTERS:
                        f.write(f'{ch}\n' + '\n'.join(''.join('#' if v else '.' for v in r) for r in new[m][(g, w, ch)]) + '\n\n')

    # --- sheets -------------------------------------------------------------
    paths = []
    for m in MODES:
        for w in lib.WEIGHTS:
            rows = []
            for g in lib.GRIDS:
                meta, G = lib.load(g, w)
                sc = scale_for(g)
                rows.append(f'{g} px {w}  ({meta["note"]})')
                before, after = [], []
                for ch in LETTERS:
                    a, b = align(lib.crop(G[ch]['bm']), new[m][(g, w, ch)])
                    before.append((ch, lib.cell(a, sc)))
                    after.append(('', lib.cell(b, sc, before=a)))
                rows.append(before)
                rows.append(after)
            paths.append(lib.sheet(rows, os.path.join(lib.IMG, f'sheet-{m}-{w}.png'),
                                   title=f'{m}: committed drawing above, redraw below (green added, pink removed)'))
    rows = []
    for w in ('regular', 'bold'):
        for g in lib.GRIDS:
            meta, G = lib.load(g, w)
            sc = scale_for(g)
            row = []
            for ch in 'AVvWM':
                src = lib.crop(G[ch]['bm'])
                row.append((f'{ch} {g} {w[0]}', lib.cell(src, sc)))
                for m in MODES:
                    row.append((m, lib.cell(new[m][(g, w, ch)], sc)))
            rows.append(row)
    paths.append(lib.sheet(rows, os.path.join(lib.IMG, 'apex.png'), title='A V v W M: committed, fixed, parity'))

    # --- proof --------------------------------------------------------------
    rows = []
    for g in (9, 12, 13, 16, 20, 24, 32):
        for w in ('regular', 'bold'):
            meta, G = lib.load(g, w)
            ims = [('committed', lib.text_bitmap(g, w, TEXT))]
            for m in MODES:
                rep = {}
                for ch in set(TEXT) & set(LETTERS):
                    src = lib.crop(G[ch]['bm'])
                    out = new[m][(g, w, ch)]
                    if out is src:
                        continue
                    box = lib.ink_box(G[ch]['bm'])
                    full = np.zeros((G[ch]['bm'].shape[0], max(G[ch]['bm'].shape[1], box[2] + out.shape[1])), bool)
                    full[box[0]:box[0] + out.shape[0], box[2]:box[2] + out.shape[1]] = out
                    rep[ch] = (full, G[ch]['advance'] + out.shape[1] - src.shape[1], G[ch]['left'])
                ims.append((m, lib.text_bitmap(g, w, TEXT, replace=rep)))
            rows.append(f'{g} px {w}')
            for lab, bm in ims:
                one, four = lib.plain(bm, 1), lib.plain(bm, 4)
                both = Image.new('RGB', (one.width + 12 + four.width, four.height), lib.PAPER)
                both.paste(one, (0, 0))
                both.paste(four, (one.width + 12, 0))
                rows.append([(lab, both)])
    paths.append(lib.sheet(rows, os.path.join(lib.IMG, 'proof.png'), title=f'"{TEXT}" at 1x and 4x: committed, fixed, parity'))
    for p in paths:
        print(p)


if __name__ == '__main__':
    main()
