"""A proof line from the built fonts, rendered by FreeType as a browser would.

    .venv/bin/python experiments/straight-diagonals/proof.py \\
        --fonts before=PATH/build after=build --sizes 9,12,16,20,24,32,48 \\
        --out experiments/straight-diagonals/img/proof-1x.png [--scale 4] \\
        [--text LINE [LINE ...]]

Each `build` directory holds IntegerSans-VF.ttf and display/IntegerSansDisplay-VF.ttf;
sizes of 25 and up come from the display family. Unhinted, as scripts/check.py
renders; a pixel that is neither ink nor paper is drawn red and counted.
"""
import argparse
import os

import freetype
import numpy as np

import lib

FLAGS = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_TARGET_NORMAL
TEXT = 'AVAVA vavav WAVY wavy MIXTAPE KNOX Hamburgefonstiv'
WGHT = {'light': 200, 'regular': 400, 'bold': 800}


def line(face, text, size):
    """(ink, gray) boolean arrays of the text set at `size` pixels."""
    h = size * 2
    ink = np.zeros((h, size * len(text) + 8), bool)
    gray = np.zeros_like(ink)
    x, base = 2.0, int(size * 1.4)
    for ch in text:
        face.load_char(ch, FLAGS)
        g = face.glyph
        b = g.bitmap
        for r in range(b.rows):
            for c in range(b.width):
                v = b.buffer[r * b.pitch + c]
                if not v:
                    continue
                yy, xx = base - g.bitmap_top + r, int(round(x)) + g.bitmap_left + c
                if 0 <= yy < h and 0 <= xx < ink.shape[1]:
                    (ink if v >= 250 else gray)[yy, xx] = True
        x += g.advance.x / 64
    both = ink | gray
    ys, xs = np.where(both)
    y0, y1, x1 = ys.min(), ys.max() + 1, xs.max() + 1
    return ink[y0:y1, :x1], gray[y0:y1, :x1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fonts', nargs='+', required=True)
    ap.add_argument('--sizes', default='9,12,16,20,24,32,48')
    ap.add_argument('--weights', default='light,regular,bold')
    ap.add_argument('--text', nargs='+', default=[TEXT], help='one or more lines; each is set from every font')
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--out', required=True)
    opt = ap.parse_args()
    rows, grays = [], 0
    for size in [int(s) for s in opt.sizes.split(',')]:
        for w in opt.weights.split(','):
            rows.append(f'{size} {w}')
            for text in opt.text:
                for f in opt.fonts:
                    label, build = f.split('=', 1)
                    path = os.path.join(build, 'IntegerSans-VF.ttf') if size <= 24 else os.path.join(build, 'display', 'IntegerSansDisplay-VF.ttf')
                    face = freetype.Face(path)
                    face.set_var_design_coords((float(size), float(WGHT[w])))
                    face.set_pixel_sizes(0, size)
                    ink, gray = line(face, text, size)
                    grays += int(gray.sum())
                    im = lib.plain(ink | gray, opt.scale)
                    if gray.any():
                        px = im.load()
                        for y, x in zip(*np.where(np.pad(gray, 2))):
                            for dy in range(opt.scale):
                                for dx in range(opt.scale):
                                    px[int(x) * opt.scale + dx, int(y) * opt.scale + dy] = (220, 0, 0)
                    rows.append([(label, im)])
    print(lib.sheet(rows, opt.out, title=f"{' | '.join(opt.text)} from the built fonts, FreeType unhinted, {opt.scale}x"))
    print('gray pixels:', grays)


if __name__ == '__main__':
    main()
