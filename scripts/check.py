"""Render Integer Sans through FreeType at every exact size and prove it is a bitmap.

    python scripts/check.py [--font build/IntegerSans-VF.ttf] [--png build/proof.png] [--glyphs glyphs]

Rendering is unhinted and antialiased, which is what browsers do with this font.
A size and weight passes when:
  - no pixel is gray (a value within 1/255 of ink or paper counts as that: grids
    that do not divide the 5040-unit em, such as 13, round coordinates by under
    0.13% of a pixel),
  - the H advance shows the right drawing was picked,
  - every glyph's ink is its source bitmap's, pixel for pixel at the scale and
    in the same place against the baseline and origin, rows over the line
    box's ascent (a raised accent) and under its descent included,
  - the glyphs with a crossbar (H A E F B P R G e f t 4) still have one (a run
    of 3+ pixels on an interior row; 2+ on grids up to 9 rows).
The PNG shows every exact size in every weight, magnified 3x with nearest
neighbour so the real pixels are visible. Each line's strip is as tall as the
ink the font can set at that size (sizes.json `box`), so nothing is cropped
from the picture or from the gray count.
"""
import argparse
import json
import os
import re

import freetype
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GLYPHS = os.path.join(HERE, '..', 'glyphs')
CROSSBARS = ['H', 'A', 'E', 'F', 'B', 'P', 'R', 'G', 'e', 'f', 't', 'four']
FLAGS = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_TARGET_NORMAL

args = argparse.ArgumentParser()
args.add_argument('--font', default=os.path.join(HERE, '..', 'build', 'IntegerSans-VF.ttf'))
args.add_argument('--png', default=os.path.join(HERE, '..', 'build', 'proof.png'))
args.add_argument('--glyphs', default=GLYPHS, help='the sources the font is compared with')
args.add_argument('--text', default='Hamburgefonstiv 0123 @&% Åéîõü')
opt = args.parse_args()
GLYPHS = opt.glyphs

info = json.load(open(os.path.join(os.path.dirname(opt.font), 'sizes.json')))
sizes = {int(k): v for k, v in info['exact'].items()}
weights = sorted(int(w) for w in info['weights'])


def source(grid, weight_key):
    """Glyph name -> (codepoints, ink) from the source files (overrides applied).
    Ink is a set of (row above the baseline, column from the origin), row 0
    sitting on the baseline; rows at or over the header's ascent are in it."""
    out = {}
    for fn in (weight_key + '.txt', weight_key + '.overrides.txt'):
        path = os.path.join(GLYPHS, str(grid), fn)
        if not os.path.exists(path):
            continue
        text = open(path).read()
        meta = dict(re.findall(r'^# (\w+): (\S+)', text, flags=re.M))
        if 'ascent' in meta:
            top = int(meta['ascent']) + int(meta.get('above', 0))
        text = re.sub(r'^# .*\n?|^#\n', '', text, flags=re.M)
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = [l for l in block.split('\n') if l]
            if lines[0].startswith('name:'):
                f = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
                name, cps, left = f['name'], [int(u[2:], 16) for u in f.get('unicode', '').split()], int(f.get('left', 0))
            else:
                out[name] = (cps, {(top - 1 - i, left + j) for i, l in enumerate(lines) for j, c in enumerate(l) if c == '#'})
    return out


def glyph_bitmap(face, cp):
    """(rows of 0..255, left, top, advance px) for a character, unhinted."""
    face.load_char(cp, FLAGS)
    g = face.glyph
    bm = g.bitmap
    rows = [[bm.buffer[r * bm.pitch + c] for c in range(bm.width)] for r in range(bm.rows)]
    return rows, g.bitmap_left, g.bitmap_top, g.advance.x / 64


def classify(v):
    return 'ink' if v >= 254 else 'paper' if v <= 1 else 'gray'


def render_line(face, text, size):
    """The sample line as an 'L' image, plus counts of ink and gray pixels.
    The strip runs from the highest ink the font has at this size to the
    lowest, with a 2px margin, so an accent over the ascent is in it."""
    box = info['box'][str(size)]
    up, down = max(box['ascent'], box['ink_up']), max(box['descent'], box['ink_down'])
    im = Image.new('L', (900, up + down + 4), 255)
    px = im.load()
    x = 2.0
    ink = gray = 0
    for ch in text:
        rows, left, top, adv = glyph_bitmap(face, ord(ch))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                if not v:
                    continue
                k = classify(v)
                ink += k == 'ink'
                gray += k == 'gray'
                xx, yy = int(round(x)) + left + c, 2 + up - top + r
                assert 0 <= yy < im.height, f'{ch!r} at {size}: ink outside the box in sizes.json'
                if 0 <= xx < im.width:
                    px[xx, yy] = 255 - v
        x += adv
    return im, ink, gray


def check_glyphs(face, grid, weight_key, scale):
    """Drawings whose rendered ink is not the source's, and missing crossbars."""
    mismatched, no_bar = [], []
    for name, (cps, src) in source(grid, weight_key).items():
        if not cps or cps[0] < 0x20:
            continue
        want = {(y * scale + dy, x * scale + dx) for y, x in src for dy in range(scale) for dx in range(scale)}
        rows, left, top, _ = glyph_bitmap(face, cps[0])
        got = {(top - 1 - r, left + c) for r, row in enumerate(rows) for c, v in enumerate(row) if classify(v) == 'ink'}
        if got != want:
            mismatched.append(f'{name}:{len(got)}/{len(want)}' + ('(moved)' if len(got) == len(want) else ''))
        if name in CROSSBARS:
            ys = sorted({y for y, _ in src})[1:-1]
            longest = 0
            for y in ys:
                xs = sorted(x for yy, x in src if yy == y)
                run = 1
                for a, b in zip(xs, xs[1:]):
                    run = run + 1 if b == a + 1 else 1
                    longest = max(longest, run)
            if longest < (2 if grid <= 9 else 3):
                no_bar.append(name)
    return mismatched, no_bar


rows_out = []
ok = True
face = freetype.Face(opt.font)
for size, grid in sorted(sizes.items()):
    for weight in weights:
        face.set_var_design_coords((float(size), float(weight)))
        face.set_pixel_sizes(0, size)
        im, ink, gray = render_line(face, opt.text, size)
        face.load_char('H', FLAGS)
        adv = face.glyph.advance.x / 64
        want = info['H'][f'{size}/{weight}']
        key = info['weights'][str(weight)]
        status = 'exact'
        if gray:
            status = f'FAIL gray={gray}'
        elif abs(adv - want) > 0.05:
            status = f'FAIL H advance {adv} (want {want})'
        else:
            mismatched, no_bar = check_glyphs(face, grid, key, size // grid)
            if mismatched:
                status = f'FAIL ink differs from source for {len(mismatched)} glyphs: ' + ' '.join(mismatched[:6])
            elif no_bar:
                status = 'FAIL crossbar missing: ' + ' '.join(no_bar)
        ok &= status == 'exact'
        print(f'{size:2d}px {key:7s} {grid}-row x{size // grid}: ink {ink:5d} gray {gray:4d} {status}')
        rows_out.append(im)
sheet = Image.new('L', (900, sum(im.height + 2 for im in rows_out) + 20), 255)
y = 10
for im in rows_out:
    sheet.paste(im, (0, y))
    y += im.height + 2
sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
sheet.save(opt.png)
print('all exact' if ok else 'FAILURES above', '->', opt.png)
raise SystemExit(0 if ok else 1)
