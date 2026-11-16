"""Spike 1: keep every glyph in one piece through the mirror and thinning passes.

    .venv/bin/python experiments/hand-drawn/spike_connected.py [--grids 11,13,14,17,18,21,23,24]

The committed drawings hold glyphs in pieces (audit.py, "broken"): the mirror
pass clears both pixels of a disagreeing pair when their mean coverage is
low, which empties a row of a thin diagonal whose two legs the hinter snapped
differently; and the thinning removes a whole mirror orbit after testing each
of its pixels alone, so an apex two pixels wide can go in one move.

A third cause is upstream of both: the monochrome render itself drops out
on strokes thinner than a pixel (5 and ß in the Light).

This runs scripts/import-inter.py unchanged on disk, with four edits applied
to its source text in memory, and writes to experiments/hand-drawn/out/connected
(ignored by git), never to glyphs/:

  1. the mirror pass is redone as a union (either side's ink wins) when it
     left the glyph in more pieces than it found it;
  2. the thinning drops a mirror orbit only if the glyph has no more pieces
     afterwards;
  3. the letters the source does not draw symmetric (a and u with dieresis,
     circumflex or ring, and the tilde) leave the mirror list;
  4. a glyph that still ends in more pieces than its outline has at four
     times the size is bridged: the clear pixel with the most coverage that
     touches two pieces is inked (with its mirror orbit), until the count
     matches.

It then re-audits both sets and draws the before/after sheet.
"""
import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit  # noqa: E402
import lib  # noqa: E402

OUT = os.path.join(lib.HERE, 'out', 'connected')
IMPORTER = os.path.join(lib.ROOT, 'scripts', 'import-inter.py')

PIECES = '''
def pieces(rows):
    """8-connected groups of ink in a list of '#'/'.' strings or bool rows."""
    ink = {(y, x) for y, r in enumerate(rows) for x, c in enumerate(r) if c == '#' or c is True}
    n = 0
    while ink:
        n += 1
        stack = [ink.pop()]
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    p = (y + dy, x + dx)
                    if p in ink:
                        ink.remove(p)
                        stack.append(p)
    return n


def bridge(rows, cover, want, orbit=None):
    """Ink the best-covered clear pixel that joins two pieces, until `want` pieces remain."""
    ink = [[c == '#' for c in r] for r in rows]
    h, w = len(ink), len(ink[0]) if ink else 0
    for _ in range(12):
        if pieces(ink) <= want:
            break
        lab, n = {}, 0
        todo = {(y, x) for y in range(h) for x in range(w) if ink[y][x]}
        while todo:
            n += 1
            stack = [todo.pop()]
            while stack:
                y, x = stack.pop()
                lab[(y, x)] = n
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        q = (y + dy, x + dx)
                        if q in todo:
                            todo.remove(q)
                            stack.append(q)
        best = None
        for y in range(h):
            for x in range(w):
                if ink[y][x] or cover[y][x] <= 0:
                    continue
                near = {lab[(y + dy, x + dx)] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (y + dy, x + dx) in lab}
                if len(near) >= 2 and (best is None or cover[y][x] > best[0]):
                    best = (cover[y][x], y, x)
        if best is None:
            break
        for py, px in (orbit(best[1], best[2]) if orbit else [(best[1], best[2])]):
            if 0 <= py < h and 0 <= px < w:
                ink[py][px] = True
    return [''.join('#' if v else '.' for v in r) for r in ink]


def _mirror_pass(rows, cover, orig, lr, tb, union=False):
'''

EDITS = [
    # 1. union fallback in the mirror pass
    ('def _mirror_pass(rows, cover, orig, lr, tb):\n', PIECES),
    ('            if c >= 0.6:\n                state = True\n',
     '            if union or c >= 0.6:\n                state = True\n'),
    ('        rows, cover = _mirror_pass(rows, cover, orig, True, False)\n',
     '        before = rows\n'
     '        rows, cover2 = _mirror_pass(before, cover, orig, True, False)\n'
     '        if pieces(rows) > pieces(before):\n'
     '            rows, cover2 = _mirror_pass(before, cover, orig, True, False, union=True)\n'
     '        cover = cover2\n'),
    ('        rows, cover = _mirror_pass(rows, cover, orig, False, True)\n',
     '        before = rows\n'
     '        rows, cover2 = _mirror_pass(before, cover, orig, False, True)\n'
     '        if pieces(rows) > pieces(before):\n'
     '            rows, cover2 = _mirror_pass(before, cover, orig, False, True, union=True)\n'
     '        cover = cover2\n'),
    # 2. an orbit leaves only if the glyph stays in as many pieces
    ('                for py, px in o:                      # a symmetric glyph loses whole orbits\n'
     '                    ink[py][px] = False\n'
     '                changed = True\n',
     '                n0 = pieces(ink) if len(o) > 1 else 0\n'
     '                for py, px in o:                      # a symmetric glyph loses whole orbits\n'
     '                    ink[py][px] = False\n'
     '                if len(o) > 1 and pieces(ink) > n0:\n'
     '                    for py, px in o:\n'
     '                        ink[py][px] = True\n'
     '                    continue\n'
     '                changed = True\n'),
    # 4. bridge what is still in more pieces than the outline at 4x
    ("    bar = bar_thickness(bitmap_rows(face.glyph.bitmap))\n",
     "    bar = bar_thickness(bitmap_rows(face.glyph.bitmap))\n"
     "    big = freetype.Face(path)\n"
     "    big.set_pixel_sizes(0, grid * 4)\n"),
    ("            lr, tb = name in SYM_LR, name in SYM_TB\n",
     "            lr, tb = name in SYM_LR, name in SYM_TB\n"
     "            orbit = None\n"),
    ("            if lr:\n                left = center_in_advance(rows, left, adv)\n",
     "            big.load_char(cp, freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_NO_HINTING)\n"
     "            big.glyph.render(freetype.FT_RENDER_MODE_MONO)\n"
     "            rows = bridge(rows, cover, pieces(bitmap_rows(big.glyph.bitmap)), orbit)\n"
     "            if lr:\n                left = center_in_advance(rows, left, adv)\n"),
    # 3. the mirror list holds only letters the source draws symmetric
    ("- {'AE', 'ae', 'logicalnot', 'quotedblbase', 'quotedblleft', 'quotedblright', 'macron'}",
     "- {'AE', 'ae', 'logicalnot', 'quotedblbase', 'quotedblleft', 'quotedblright', 'macron', '~', 'asciitilde',\n"
     "     'adieresis', 'acircumflex', 'aring', 'udieresis', 'ucircumflex'}"),
]


def run_importer(grids):
    src = open(IMPORTER).read()
    for old, new in EDITS:
        assert src.count(old) == 1, old
        src = src.replace(old, new)
    argv = sys.argv
    sys.argv = [IMPORTER, '--grids', grids, '--out', os.path.join(OUT, 'glyphs')]
    try:
        exec(compile(src, IMPORTER, 'exec'), {'__file__': IMPORTER, '__name__': '__main__'})
    finally:
        sys.argv = argv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', default='11,13,14,17,18,21,23,24')
    ap.add_argument('--skip-render', action='store_true')
    opt = ap.parse_args()
    grids = [int(g) for g in opt.grids.split(',')]
    if not opt.skip_render:
        run_importer(opt.grids)
    root = os.path.join(OUT, 'glyphs')

    def count(fonts):
        """Glyph drawings (Latin-1) in more pieces than the same glyph at the largest rendered grid."""
        ref = {}
        out = []
        for (g, w), F in sorted(fonts.items()):
            for ch, gl in F['G'].items():
                out.append((g, w, ch, audit.topology(gl['bm'])[0]))
        return out

    before = {(g, w): audit.integer_font(g, w) for g in grids for w in lib.WEIGHTS}
    after = {(g, w): audit.integer_font(g, w, root=root) for g in grids for w in lib.WEIGHTS}
    # the expected piece count of each glyph: its mode over the committed sizes 25 to 48
    expect = {}
    for w in lib.WEIGHTS:
        big = [audit.integer_font(g, w) for g in range(25, 49)]
        for ch in big[0]['G']:
            expect[(w, ch)] = collections.Counter(audit.topology(F['G'][ch]['bm'])[0] for F in big).most_common(1)[0][0]
    for bad in ('~', '\u00e4', '\u00e2', '\u00e5', '\u00fc', '\u00fb'):
        for w in lib.WEIGHTS:
            expect[(w, bad)] = 3 if bad in '\u00e4\u00fc' else 2 if bad != '~' else 1

    def broken(fonts):
        return {(g, w, ch) for (g, w), F in fonts.items() for ch, gl in F['G'].items()
                if audit.topology(gl['bm'])[0] > expect[(w, ch)]}

    b0, b1 = broken(before), broken(after)
    changed = sum(1 for key in before for ch in before[key]['G']
                  if not np.array_equal(before[key]['G'][ch]['bm'], after[key]['G'][ch]['bm']))
    total = sum(len(F['G']) for F in before.values())
    print(f'grids {opt.grids}: {total} drawings, {changed} changed')
    print(f'in more pieces than expected: before {len(b0)}, after {len(b1)}')
    if b1:
        print('  still broken: ' + ' '.join(f'{ch}@{g}{w[0]}' for g, w, ch in sorted(b1)))
    for name in ('lr asymmetric glyphs', 'kinks', 'blob glyphs', 'accented base differs'):
        s0 = sum(audit.audit_font(F)[0][name] for F in before.values())
        s1 = sum(audit.audit_font(F)[0][name] for F in after.values())
        print(f'{name}: before {s0}, after {s1}')

    # sheet: the broken ones, before over after
    picks = [(11, 'regular', 'W'), (13, 'regular', 'v'), (13, 'regular', 'w'), (13, 'regular', '5'), (14, 'regular', 'A'),
             (17, 'light', 'A'), (18, 'light', 'A'), (18, 'light', 'W'), (18, 'light', '8'), (21, 'light', 'V'),
             (23, 'light', 'n'), (24, 'light', 'u'), (16, 'regular', '\u00e4'), (16, 'regular', '\u00fb'), (24, 'regular', '~')]
    picks = [p for p in picks if p[0] in grids or p[0] == 16]
    top, bot = [], []
    for g, w, ch in picks:
        if (g, w) not in before:
            continue
        a, b = before[(g, w)]['G'][ch]['bm'], after[(g, w)]['G'][ch]['bm']
        wd = max(a.shape[1], b.shape[1])
        a = np.pad(a, ((0, 0), (0, wd - a.shape[1])))
        b = np.pad(b, ((0, 0), (0, wd - b.shape[1])))
        ys, xs = np.where(a | b)
        sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
        top.append((f'{ch} {g} {w}', lib.cell(a[sl], 9)))
        bot.append((f'{ch} {g} {w}', lib.cell(b[sl], 9, before=a[sl])))
    half = (len(top) + 1) // 2
    rows = ['committed', top[:half], 'connected mirror and thinning (green added, pink removed)', bot[:half],
            'committed', top[half:], 'connected mirror and thinning', bot[half:]]
    print(lib.sheet(rows, os.path.join(lib.IMG, 'spike-connected.png'),
                    title='Spike 1: one piece through the mirror and thinning passes'))


if __name__ == '__main__':
    main()
