"""Render Integer through FreeType at every exact size and prove it is a bitmap.

    python scripts/check.py [--font build/Integer-VF.ttf] [--png build/proof.png]

Antialiasing is on; a size passes when no pixel is gray. The PNG shows every
exact size, Regular and Bold, magnified 3x with nearest-neighbour so the real
pixels are visible.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
args = argparse.ArgumentParser()
args.add_argument('--font', default=os.path.join(HERE, '..', 'build', 'Integer-VF.ttf'))
args.add_argument('--png', default=os.path.join(HERE, '..', 'build', 'proof.png'))
args.add_argument('--text', default='Hamburgefonstiv 0123 @&% Åéîõü')
opt = args.parse_args()

sizes = json.load(open(os.path.join(os.path.dirname(opt.font), 'sizes.json')))['exact']
sizes = {int(k): v for k, v in sizes.items()}
sheet = Image.new('L', (900, sum(s + 6 for s in sizes) * 2 + 20), 255)
draw = ImageDraw.Draw(sheet)
y = 10
ok = True
for size, grid in sorted(sizes.items()):
    for weight in (400, 700):
        font = ImageFont.truetype(opt.font, size)
        tags = [a['name'] for a in font.get_variation_axes()]
        font.set_variation_by_axes([size, weight])
        im = Image.new('L', (900, size + 6), 255)
        ImageDraw.Draw(im).text((2, 2), opt.text, font=font, fill=0)
        hist = im.histogram()
        gray = sum(hist[1:255])
        ink = hist[0]
        adv = font.getlength('HHHHHHHHHH') / 10
        unit = 8 if weight == 700 else 7                 # a 5-wide letter advances 7, Bold 8
        got = next((g for g in (16, 14, 12, 11, 10, 9, 8) if abs(adv - size * unit / g) < 0.05), None)
        status = 'exact' if gray == 0 and got == grid else f'FAIL gray={gray} grid={got}'
        ok &= status == 'exact'
        print(f'{size:2d}px {"Bold" if weight == 700 else "Regular":7s} {grid}-row x{size // grid}: ink {ink:5d} gray {gray:4d} {status}')
        sheet.paste(im, (0, y))
        y += size + 6
sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
sheet.save(opt.png)
print('all exact' if ok else 'FAILURES above', '->', opt.png)
raise SystemExit(0 if ok else 1)
