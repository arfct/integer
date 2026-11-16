"""Shared helpers for the hand-drawn audit and spikes: load the committed
drawings, and draw magnified contact sheets with a visible pixel grid.

Nothing here writes to glyphs/ or touches the importer.
"""
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
GLYPHS = os.path.join(ROOT, 'glyphs')
IMG = os.path.join(HERE, 'img')
WEIGHTS = ('light', 'regular', 'bold')
GRIDS = list(range(7, 49))


def parse(path):
    """A source file as (meta, {name: glyph}); same reading as scripts/build.py."""
    text = open(path).read()
    meta = dict(re.findall(r'^# (\w+): (\S+)', text, flags=re.M))
    note = re.search(r'^# \((.*)\)\.', text, flags=re.M)
    meta['note'] = note.group(1) if note else ''
    for key in ('stem', 'bar'):
        m = re.search(key + r' (\d+)px', meta['note'])
        meta[key] = int(m.group(1)) if m else 1
    m = re.search(r'smear (\d+)', meta['note'])
    meta['smear'] = int(m.group(1)) if m else 0
    text = re.sub(r'^# .*\n?|^#\n', '', text, flags=re.M)
    glyphs = {}
    cur = None
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = [l for l in block.split('\n') if l]
        if lines[0].startswith('name:'):
            f = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
            cur = glyphs[f['name']] = {'name': f['name'],
                                       'unicode': [int(u[2:], 16) for u in f.get('unicode', '').split()],
                                       'advance': int(f['advance']), 'left': int(f.get('left', 0)), 'rows': []}
        else:
            cur['rows'] = lines
    for g in glyphs.values():
        w = max(len(r) for r in g['rows']) if g['rows'] else 0
        g['bm'] = np.array([[c == '#' for c in r.ljust(w, '.')] for r in g['rows']], dtype=bool).reshape(len(g['rows']), w)
    return meta, glyphs


_cache = {}


def load(grid, weight, root=None):
    """(meta, glyphs) for one committed grid and weight, overrides applied.
    `root` reads a spike's own output directory instead of glyphs/."""
    key = (grid, weight, root)
    if key not in _cache:
        path = os.path.join(root or GLYPHS, str(grid), weight + '.txt')
        meta, glyphs = parse(path)
        over = path[:-4] + '.overrides.txt'
        if os.path.exists(over):
            glyphs.update(parse(over)[1])
        for k in ('grid', 'ascent', 'descent', 'cap', 'xheight'):
            meta[k] = int(meta[k])
        _cache[key] = (meta, glyphs)
    return _cache[key]


def ink_box(bm):
    """(y0, y1, x0, x1) inclusive of the ink, or None when empty."""
    ys, xs = np.where(bm)
    if not len(ys):
        return None
    return ys.min(), ys.max(), xs.min(), xs.max()


def crop(bm):
    b = ink_box(bm)
    if b is None:
        return bm[:0, :0]
    return bm[b[0]:b[1] + 1, b[2]:b[3] + 1]


def bearings(g):
    """(left bearing, ink width, right bearing) in pixels; None for empty glyphs."""
    b = ink_box(g['bm'])
    if b is None:
        return None
    lsb = b[2] + g['left']
    w = b[3] - b[2] + 1
    return lsb, w, g['advance'] - lsb - w


def text_bitmap(grid, weight, text, glyphs=None, gap=0):
    """Set a string from the committed drawings (or a replacement dict) into one array."""
    meta, base = load(grid, weight)
    glyphs = glyphs or base
    cmap = {u: g for g in base.values() for u in g['unicode']}
    h = meta['ascent'] + meta['descent']
    cols = []
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        g = glyphs.get(g['name'], g)
        cell = np.zeros((h, g['advance'] + gap), dtype=bool)
        bm = g['bm']
        for y in range(min(h, bm.shape[0])):
            for x in range(bm.shape[1]):
                xx = x + g['left']
                if bm[y, x] and 0 <= xx < cell.shape[1]:
                    cell[y, xx] = True
        cols.append(cell)
    return np.hstack(cols) if cols else np.zeros((h, 1), dtype=bool)


# --- drawing ---------------------------------------------------------------
def font(size=11):
    for p in ('/System/Library/Fonts/Menlo.ttc', '/System/Library/Fonts/Monaco.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


INK = (20, 20, 24)
PAPER = (255, 255, 255)
GRID = (226, 226, 232)
MARK = (226, 60, 50)       # defect highlight
ADD = (40, 150, 70)        # pixel added by a spike
DROP = (236, 150, 150)     # pixel removed by a spike


def cell(bm, scale, marks=None, before=None, pad=1):
    """One magnified bitmap with a pixel grid. `marks` is a bool array of
    pixels to draw in red; `before` colours the difference against an earlier
    bitmap of the same shape (green added, pink removed)."""
    bm = np.pad(bm, pad)
    if marks is not None:
        marks = np.pad(marks, pad)
    if before is not None:
        before = np.pad(before, pad)
    h, w = bm.shape
    im = Image.new('RGB', (w * scale + 1, h * scale + 1), PAPER)
    d = ImageDraw.Draw(im)
    for y in range(h):
        for x in range(w):
            col = None
            if bm[y, x]:
                col = INK
                if before is not None and not before[y, x]:
                    col = ADD
                if marks is not None and marks[y, x]:
                    col = MARK
            elif before is not None and before[y, x]:
                col = DROP
            elif marks is not None and marks[y, x]:
                col = (250, 205, 200)
            if col:
                d.rectangle([x * scale, y * scale, (x + 1) * scale, (y + 1) * scale], fill=col)
    if scale >= 4:
        for x in range(w + 1):
            d.line([x * scale, 0, x * scale, h * scale], fill=GRID)
        for y in range(h + 1):
            d.line([0, y * scale, w * scale, y * scale], fill=GRID)
    return im


def sheet(rows, path, title=None, gap=14, label_h=16, margin=16):
    """rows: list of rows; each row is a list of (label, PIL image) or a str
    (a section heading). Writes a PNG and returns its path."""
    f, fb = font(11), font(13)
    heights, widths = [], []
    for row in rows:
        if isinstance(row, str):
            heights.append(26)
            widths.append(int(fb.getlength(row)) + 4)
        else:
            heights.append(max(im.height for _, im in row) + label_h * (1 + max(lab.count('\n') for lab, _ in row)) + gap)
            widths.append(sum(max(im.width, int(max(f.getlength(s) for s in lab.split('\n')))) + gap for lab, im in row))
    top = 34 if title else 0
    W = max(widths) + 2 * margin
    if title:
        W = max(W, int(fb.getlength(title)) + 2 * margin)
    H = sum(heights) + 2 * margin + top
    out = Image.new('RGB', (W, H), PAPER)
    d = ImageDraw.Draw(out)
    if title:
        d.text((margin, margin - 4), title, fill=INK, font=fb)
    y = margin + top
    for row, hh in zip(rows, heights):
        if isinstance(row, str):
            d.text((margin, y + 6), row, fill=(90, 90, 100), font=fb)
        else:
            x = margin
            nl = 1 + max(lab.count('\n') for lab, _ in row)
            for lab, im in row:
                d.multiline_text((x, y), lab, fill=(90, 90, 100), font=f, spacing=2)
                out.paste(im, (x, y + label_h * nl))
                x += max(im.width, int(max(f.getlength(s) for s in lab.split('\n')))) + gap
        y += hh
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)
    return path
