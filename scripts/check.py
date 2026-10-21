"""Render Integer Sans through FreeType at every exact size and prove it is a bitmap.

    python scripts/check.py [--font build/IntegerSans-VF.ttf] [--png build/proof.png]

Rendering is unhinted and antialiased, which is what browsers do with this font.
A size and weight passes when:
  - no pixel is gray (a value within 1/255 of ink or paper counts as that: grids
    that do not divide the 5040-unit em, such as 13, round coordinates by under
    0.13% of a pixel),
  - the H advance shows the right drawing was picked,
  - every glyph's ink pixel count equals its source bitmap's, times the scale,
  - the glyphs with a crossbar (H A E F B P R G e f t 4) still have one (a run
    of 3+ pixels on an interior row; 2+ on grids up to 9 rows).
The PNG shows every exact size in every weight, magnified 3x with nearest
neighbour so the real pixels are visible.
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
args.add_argument('--text', default='Hamburgefonstiv 0123 @&% Åéîõü')
opt = args.parse_args()

info = json.load(open(os.path.join(os.path.dirname(opt.font), 'sizes.json')))
sizes = {int(k): v for k, v in info['exact'].items()}
weights = sorted(int(w) for w in info['weights'])


def source(grid, weight_key):
    """Glyph name -> (codepoints, rows) from the source files (overrides applied)."""
    out = {}
    for fn in (weight_key + '.txt', weight_key + '.overrides.txt'):
        path = os.path.join(GLYPHS, str(grid), fn)
        if not os.path.exists(path):
            continue
        text = re.sub(r'^# .*\n?|^#\n', '', open(path).read(), flags=re.M)
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = [l for l in block.split('\n') if l]
            if lines[0].startswith('name:'):
                f = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
                name, cps = f['name'], [int(u[2:], 16) for u in f.get('unicode', '').split()]
            else:
                out[name] = (cps, lines)
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
    """The sample line as an 'L' image, plus counts of ink and gray pixels."""
    im = Image.new('L', (900, size + 6), 255)
    px = im.load()
    x = 2.0
    ink = gray = 0
    for ch in text:
        rows, left, top, adv = glyph_bitmap(face, ord(ch))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                xx, yy = int(round(x)) + left + c, 2 + (size - 1) - top + r + 1
                if 0 <= xx < im.width and 0 <= yy < im.height and v:
                    px[xx, yy] = 255 - v
                    k = classify(v)
                    ink += k == 'ink'
                    gray += k == 'gray'
        x += adv
    return im, ink, gray


def check_glyphs(face, grid, weight_key, scale):
    """Ink-count mismatches against the source, and missing crossbars."""
    mismatched, no_bar = [], []
    for name, (cps, lines) in source(grid, weight_key).items():
        if not cps or cps[0] < 0x20:
            continue
        want = sum(l.count('#') for l in lines) * scale * scale
        rows, *_ = glyph_bitmap(face, cps[0])
        got = sum(1 for row in rows for v in row if classify(v) == 'ink')
        if got != want:
            mismatched.append(f'{name}:{got}/{want}')
        if name in CROSSBARS:
            inked = [l for l in lines if '#' in l][1:-1]
            if max((len(m) for l in inked for m in re.findall(r'#+', l)), default=0) < (2 if grid <= 9 else 3):
                no_bar.append(name)
    return mismatched, no_bar


sheet = Image.new('L', (900, sum(s + 6 for s in sizes) * len(weights) + 20), 255)
y = 10
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
        sheet.paste(im, (0, y))
        y += size + 6
sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
sheet.save(opt.png)
print('all exact' if ok else 'FAILURES above', '->', opt.png)
raise SystemExit(0 if ok else 1)
