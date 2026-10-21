"""Render a labelled specimen of common sizes through unhinted FreeType.

    python scripts/specimen.py [--sizes 9,10,11,12,13,14,16,18,20,24,32,48] [--out build/specimen.png]

Writes the sheet at actual pixels and a 3x nearest-neighbour copy next to it.
"""
import argparse
import json
import os

import freetype
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_TARGET_NORMAL
args = argparse.ArgumentParser()
args.add_argument('--font', default=os.path.join(HERE, '..', 'build', 'IntegerSans-VF.ttf'))
args.add_argument('--sizes', default='9,10,11,12,13,14,16,18,20,24,32,48')
args.add_argument('--text', default='The quick brown fox jumps over the lazy dog 0123456789 @&% Åéîõü')
args.add_argument('--out', default=os.path.join(HERE, '..', 'build', 'specimen.png'))
opt = args.parse_args()

info = json.load(open(os.path.join(os.path.dirname(opt.font), 'sizes.json')))
sizes = [int(s) for s in opt.sizes.split(',')]
weights = [(200, 'Light'), (400, 'Regular'), (800, 'Bold')]
face = freetype.Face(opt.font)
label_font = ImageFont.load_default(size=11)
LABEL_W, PAD = 150, 6


def draw_text(im, x0, y_base, text):
    px = im.load()
    x = float(x0)
    for ch in text:
        face.load_char(ch, FLAGS)
        g = face.glyph
        bm = g.bitmap
        for r in range(bm.rows):
            for c in range(bm.width):
                v = bm.buffer[r * bm.pitch + c]
                if v:
                    xx, yy = int(round(x)) + g.bitmap_left + c, y_base - g.bitmap_top + r
                    if 0 <= xx < im.width and 0 <= yy < im.height:
                        px[xx, yy] = 255 - v
        x += g.advance.x / 64
    return int(x)


rows = []
for size in sizes:
    for w, name in weights:
        rows.append((size, w, name))
height = sum(int(s * 1.5) + PAD for s, _, _ in rows) + 2 * PAD
im = Image.new('L', (1400, height), 255)
d = ImageDraw.Draw(im)
y = PAD
for size, w, name in rows:
    exact = str(size) in info['exact']
    grid = info['exact'].get(str(size))
    face.set_var_design_coords((float(size), float(w)))
    face.set_pixel_sizes(0, size)
    line = int(size * 1.5)
    base = y + int(size * 1.1)
    label = f'{size}px {name}' + (f'  {grid}-row' + (f' x{size // grid}' if size // grid > 1 else '') if exact else '  resampled')
    d.text((PAD, y + line // 2 - 6), label, font=label_font, fill=96 if exact else 160)
    draw_text(im, LABEL_W, base, opt.text)
    y += line + PAD
im.save(opt.out)
big = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
big.save(opt.out.replace('.png', '-3x.png'))
print(opt.out, im.size, 'and the 3x copy')
