"""Render Integer Sans through FreeType at every exact size and prove it is a bitmap.

    python scripts/check.py [--font build/IntegerSans-VF.ttf] [--png build/proof.png]

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
args.add_argument('--font', default=os.path.join(HERE, '..', 'build', 'IntegerSans-VF.ttf'))
args.add_argument('--png', default=os.path.join(HERE, '..', 'build', 'proof.png'))
args.add_argument('--text', default='Hamburgefonstiv 0123 @&% Åéîõü')
opt = args.parse_args()

info = json.load(open(os.path.join(os.path.dirname(opt.font), 'sizes.json')))
sizes = {int(k): v for k, v in info['exact'].items()}
weights = sorted(int(w) for w in info['weights'])
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
        gray = sum(hist[1:255])
        ink = hist[0]
        adv = font.getlength('HHHHHHHHHH') / 10
        want = info['H'][f'{size}/{weight}']               # H advance in px if the right drawing was picked
        right = abs(adv - want) < 0.05
        status = 'exact' if gray == 0 and right else f'FAIL gray={gray} H-advance={adv} (want {want})'
        ok &= status == 'exact'
        print(f'{size:2d}px {info["weights"][str(weight)]:7s} {grid}-row x{size // grid}: ink {ink:5d} gray {gray:4d} {status}')
        sheet.paste(im, (0, y))
        y += size + 6
sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
sheet.save(opt.png)
print('all exact' if ok else 'FAILURES above', '->', opt.png)
raise SystemExit(0 if ok else 1)
