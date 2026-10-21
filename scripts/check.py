"""Render Integer Sans through FreeType at every exact size and prove it is a bitmap.

    python scripts/check.py [--font build/IntegerSans-VF.ttf] [--png build/proof.png]

Antialiasing is on; a size passes when no pixel is gray (a value within 1/255
of ink or paper counts as that: grids that do not divide the 5040-unit em,
such as 13, round coordinates by under 0.13% of a pixel). The PNG shows every
exact size, Regular and Bold, magnified 3x with nearest-neighbour so the real
pixels are visible.
"""
import argparse
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
args = argparse.ArgumentParser()
args.add_argument('--font', default=os.path.join(HERE, '..', 'build', 'IntegerSans-VF.ttf'))
args.add_argument('--png', default=os.path.join(HERE, '..', 'build', 'proof.png'))
args.add_argument('--text', default='Hamburgefonstiv 0123 @&% Åéîõü')
opt = args.parse_args()

info = json.load(open(os.path.join(os.path.dirname(opt.font), 'sizes.json')))
sizes = {int(k): v for k, v in info['exact'].items()}
weights = sorted(int(w) for w in info['weights'])
GLYPHS = os.path.join(HERE, '..', 'glyphs')


def source_ink(grid, weight_key):
    """Codepoint -> number of ink pixels in the source bitmap (overrides applied)."""
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
                cur = f.get('unicode', '').split()
            else:
                for u in cur:
                    out[int(u[2:], 16)] = sum(l.count('#') for l in lines)
    return out


CROSSBARS = ['H', 'A', 'E', 'F', 'B', 'P', 'R', 'G', 'e', 'f', 't', 'four']


def source_rows(grid, weight_key):
    """Glyph name -> bitmap rows from the source (overrides applied)."""
    out = {}
    for fn in (weight_key + '.txt', weight_key + '.overrides.txt'):
        path = os.path.join(GLYPHS, str(grid), fn)
        if not os.path.exists(path):
            continue
        text = re.sub(r'^# .*\n?|^#\n', '', open(path).read(), flags=re.M)
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = [l for l in block.split('\n') if l]
            if lines[0].startswith('name:'):
                name = lines[0].split(':', 1)[1].strip()
            else:
                out[name] = lines
    return out


def missing_crossbars(grid, weight_key):
    """Glyphs with a crossbar whose source has no horizontal run of 3+ on an interior row."""
    bad = []
    rows = source_rows(grid, weight_key)
    for name in CROSSBARS:
        r = [l for l in rows.get(name, []) if '#' in l]
        interior = r[1:-1]
        longest = max((len(m) for l in interior for m in re.findall(r'#+', l)), default=0)
        if longest < 3:
            bad.append(name)
    return bad


def ink_mismatches(font, size, grid, weight_key, scale):
    """Glyphs whose rendered ink pixel count differs from the source bitmap's."""
    bad = []
    for cp, want in source_ink(grid, weight_key).items():
        if cp < 0x20 or cp == 0x7f:
            continue
        im = Image.new('L', (size * 4, size * 3), 255)
        ImageDraw.Draw(im).text((size, size * 2), chr(cp), font=font, fill=0, anchor='ls')
        got = sum(im.histogram()[:2])
        if got != want * scale * scale:
            bad.append(f'U+{cp:04X}:{got}/{want * scale * scale}')
    return bad


sheet = Image.new('L', (900, sum(s + 6 for s in sizes) * len(weights) + 20), 255)
draw = ImageDraw.Draw(sheet)
y = 10
ok = True
for size, grid in sorted(sizes.items()):
    for weight in weights:
        font = ImageFont.truetype(opt.font, size)
        tags = [a['name'] for a in font.get_variation_axes()]
        font.set_variation_by_axes([size, weight])
        im = Image.new('L', (900, size + 6), 255)
        ImageDraw.Draw(im).text((2, 2), opt.text, font=font, fill=0)
        hist = im.histogram()
        gray = sum(hist[2:254])                           # within 1/255 of ink or paper is rounding, not blur
        ink = hist[0] + hist[1]
        adv = font.getlength('HHHHHHHHHH') / 10
        want = info['H'][f'{size}/{weight}']               # H advance in px if the right drawing was picked
        right = abs(adv - want) < 0.05
        status = 'exact' if gray == 0 and right else f'FAIL gray={gray} H-advance={adv} (want {want})'
        if status == 'exact':
            bad = ink_mismatches(font, size, grid, info['weights'][str(weight)], size // grid)
            if bad:
                status = f'FAIL ink differs from source for {len(bad)} glyphs: ' + ' '.join(bad[:6])
        if status == 'exact' and size == grid:
            bad = missing_crossbars(grid, info['weights'][str(weight)])
            if bad:
                status = 'FAIL crossbar missing: ' + ' '.join(bad)
        ok &= status == 'exact'
        print(f'{size:2d}px {info["weights"][str(weight)]:7s} {grid}-row x{size // grid}: ink {ink:5d} gray {gray:4d} {status}')
        sheet.paste(im, (0, y))
        y += size + 6
sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
sheet.save(opt.png)
print('all exact' if ok else 'FAILURES above', '->', opt.png)
raise SystemExit(0 if ok else 1)
