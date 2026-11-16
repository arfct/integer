"""The current state: a contact sheet of the worst offenders the audit finds
in the committed drawings, grouped by defect and labelled.

    .venv/bin/python experiments/hand-drawn/offenders.py

Red marks the pixels the audit counts: a kinked run, a pixel that differs
from the part the glyph should share, a blob's core.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit  # noqa: E402
import lib  # noqa: E402

_fonts = {}


def font(g, w):
    if (g, w) not in _fonts:
        _fonts[(g, w)] = audit.integer_font(g, w)
    return _fonts[(g, w)]


def one(g, w, ch, scale, mark=None, note=''):
    """A glyph cropped to its ink (plus any marks), magnified."""
    F = font(g, w)
    bm = F['G'][ch]['bm']
    marks = None
    if mark == 'kinks':
        marks = audit.jaggies(bm, ch)[3]
    elif mark == 'blob':
        marks = audit.blobs(bm, F['k'], F['h'])
    elif mark == 'orphans':
        marks = audit.orphans(bm)
    elif mark == 'edge':
        marks = np.zeros(bm.shape, dtype=bool)
        marks[:, 0] = bm[:, 0]
    b = lib.ink_box(bm)
    sl = (slice(b[0], b[1] + 1), slice(0 if mark == 'edge' else b[2], b[3] + 1))
    lab = f'{ch} {g} {w}' + (f'\n{note}' if note else '')
    return lab, lib.cell(bm[sl], scale, marks=None if marks is None else marks[sl])


def versus(g, w, a, b, f, scale, note):
    """Glyph b, with the pixels that differ from f(glyph a) in red."""
    F = font(g, w)
    A, B = audit.band(F, a, F['xtop']), audit.band(F, b, F['xtop'])
    want = f(A)
    h, wd = max(want.shape[0], B.shape[0]), max(want.shape[1], B.shape[1])
    W = np.zeros((h, wd), dtype=bool)
    Bp = np.zeros((h, wd), dtype=bool)
    W[:want.shape[0], wd - want.shape[1]:] = want          # stems of d and q sit at the right
    Bp[:B.shape[0], wd - B.shape[1]:] = B
    return f'{b} {g} {w}\n{note}', lib.cell(Bp, scale, marks=W ^ Bp)


def line(g, w, text, scale, note=''):
    bm = lib.text_bitmap(g, w, text, gap=1)
    ys = np.where(bm.any(axis=1))[0]
    return f'"{text}" {g} {w}' + (f'\n{note}' if note else ''), lib.cell(bm[ys.min():ys.max() + 1], scale)


def mir(a):
    return a[:, ::-1]


rows = [
    'Glyphs in pieces: 67 ASCII drawings hold more pieces of ink than the same glyph at 25 to 48',
    [one(11, 'regular', 'W', 9), one(13, 'regular', 'v', 9), one(13, 'regular', '5', 9), one(14, 'regular', 'A', 9),
     one(18, 'light', 'A', 8), one(18, 'light', '8', 8), one(21, 'light', 'V', 7), one(24, 'light', 'u', 7)],
    'Mirrored by mistake: a and u under a dieresis, circumflex or ring are on the mirror list, and so is the tilde',
    [line(12, 'regular', 'a\u00e4\u00e2\u00e5 o\u00f6', 9, 'the a is gone'), line(16, 'regular', 'u\u00fc\u00fb', 7, 'the stem is gone'),
     one(24, 'regular', '~', 9), one(40, 'regular', '~', 6)],
    'Cut off at the left: 799 Latin-1 drawings have a negative left offset and ink on the edge of their box (red)',
    [one(32, 'bold', 'j', 5, 'edge', 'the hook is cut'), one(32, 'bold', '\u00cc', 5, 'edge', 'the grave is cut'),
     one(24, 'regular', 'j', 7, 'edge')],
    'Counters closed or added: 102 ASCII drawings have fewer counters than at 25 to 48, 88 have more',
    [one(20, 'light', '5', 7, None, 'flag meets bowl'), one(32, 'regular', '5', 5), one(9, 'regular', '9', 12), one(9, 'regular', 's', 12),
     one(8, 'regular', 'a', 12), one(8, 'regular', '6', 12), one(10, 'regular', '@', 10)],
    'Parts not shared: d against b mirrored, q against p mirrored (red: pixels that differ); 235 of 756 pairs differ',
    [one(9, 'regular', 'b', 12), versus(9, 'regular', 'b', 'd', mir, 12, 'vs b mirrored'), one(9, 'regular', 'p', 12),
     versus(9, 'regular', 'p', 'q', mir, 12, 'vs p mirrored'), versus(32, 'regular', 'b', 'd', mir, 5, 'vs b mirrored'),
     versus(40, 'bold', 'p', 'q', mir, 4, 'vs p mirrored'), versus(48, 'regular', 'b', 'd', mir, 4, 'vs b mirrored')],
    'Staircases: hard kinks (a run two or more longer or shorter than both neighbours) in red',
    [one(24, 'regular', 'A', 7, 'kinks'), one(24, 'regular', 'y', 7, 'kinks'), one(32, 'regular', 'M', 5, 'kinks'),
     one(32, 'regular', 'W', 5, 'kinks'), one(40, 'regular', 'C', 4, 'kinks'), one(24, 'bold', 'w', 7, 'kinks')],
    'Stems and bars that cannot centre, and bars that disagree: T on the wrong parity, H on an even cap, T against H',
    [one(12, 'bold', 'T', 9, None, 'stem off centre'), one(20, 'regular', 'T', 7, None, 'stem off centre'),
     one(16, 'regular', 'H', 7, None, 'bar above centre'), line(19, 'regular', 'TH', 7, 'T bar 2, H bar 1'),
     line(28, 'regular', 'TEH', 5, 'T bar 1, H bar 2')],
    'Dots drawn per glyph: the same size gives the period, colon, i and ! different dots',
    [line(13, 'regular', 'i.:;!?', 9), line(22, 'regular', 'i.:;!?', 7), line(24, 'regular', 'i.:;!?', 7), line(8, 'bold', 'ij!', 11, 'dot merged')],
    'Blobs and strays: a solid square wider than the stroke (red core); pixels with no orthogonal neighbour in a 2 px weight',
    [one(32, 'bold', 'M', 5, 'blob'), one(12, 'bold', 'X', 9, 'blob'), one(10, 'bold', '&', 10, 'blob'),
     one(20, 'regular', '~', 9, 'orphans'), one(18, 'regular', '%', 8, 'orphans'), one(17, 'regular', 'm', 8, 'orphans')],
]
print(lib.sheet(rows, os.path.join(lib.IMG, 'current-worst.png'),
                title='Integer Sans, committed drawings: the worst offenders by defect (audit.py)'))
