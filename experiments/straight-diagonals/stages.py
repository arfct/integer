"""Where in the importer do straight outline edges stop being straight?

    .venv/bin/python experiments/straight-diagonals/stages.py [--grids 9,12,20] [--dump A:20:bold]

Runs the importer's own functions (the script's source up to its main loop,
executed here; nothing is written to glyphs/) and scores the study letters
after each stage with measure.score:

  outline   the source instance, y not warped, no hinting, 1-bit render
  warped    y warped onto the grid's metric rows, no hinting, 1-bit render
  hinted    warped, FreeType autohinter, 1-bit render: what render_font starts from
  mirror    after the first symmetrize() (mirrored letters only; others unchanged)
  thinned   after the first thin()
  final     after the second symmetrize(), thin() and bridge(): the committed drawing
and two side runs from `hinted`:
  thin only     thin() with no mirroring at all
  mirror only   symmetrize() twice with no thinning

`final` is compared with the committed drawing; a mismatch means this trace
does not reproduce the importer (letters the derivation stage rebuilds are
not in the study set).
"""
import argparse
import collections
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ap = argparse.ArgumentParser()
ap.add_argument('--grids', default='7,9,10,12,13,16,20,24,32,48')
ap.add_argument('--dump', help='letter:grid:weight, print every stage as text')
mine = ap.parse_args()

import lib          # noqa: E402
import measure      # noqa: E402

SRC = os.path.join(lib.ROOT, 'scripts', 'import-inter.py')
code = open(SRC).read()
code = code[:code.index('tmp = tempfile.mkdtemp()')]
imp = {'__file__': SRC, '__name__': 'importer'}
argv, sys.argv = sys.argv, [SRC]
exec(compile(code, SRC, 'exec'), imp)
sys.argv = argv

freetype = imp['freetype']
STAGES = ('outline', 'warped', 'hinted', 'mirror', 'thinned', 'final', 'thin only', 'mirror only')
CHARS = measure.GLYPHS


def to_bm(rows):
    if not rows:
        return np.zeros((0, 0), bool)
    return np.array([[c == '#' for c in r] for r in rows], dtype=bool)


def mono(path, grid, ch, hint):
    face = freetype.Face(path)
    if hint:
        prop = imp['_XHeightProp'](imp['ctypes'].cast(face._FT_Face, imp['ctypes'].c_void_p).value, 0)
        freetype.raw.FT_Property_Set(freetype.get_handle(), b'autofitter', b'increase-x-height', imp['ctypes'].byref(prop))
    face.set_pixel_sizes(0, grid)
    flags = freetype.FT_LOAD_TARGET_MONO | (freetype.FT_LOAD_FORCE_AUTOHINT if hint else freetype.FT_LOAD_NO_HINTING)
    face.load_char(ch, flags)
    g = face.glyph
    g.render(freetype.FT_RENDER_MODE_MONO)
    rows, left, top = imp['bitmap_rows'](g.bitmap), g.bitmap_left, g.bitmap_top
    face.load_char(ch, flags)
    g = face.glyph
    g.render(freetype.FT_RENDER_MODE_NORMAL)
    gray, gl, gt = imp['bitmap_rows'](g.bitmap), g.bitmap_left, g.bitmap_top
    cover = [[0.0] * len(rows[0]) for _ in rows]
    for y, r in enumerate(gray):
        for x, v in enumerate(r):
            yy, xx = y + (top - gt), x + (gl - left)
            if 0 <= yy < len(rows) and 0 <= xx < len(rows[0]):
                cover[yy][xx] = v / 255.0
    return rows, cover


def trace(path_plain, path_warped, grid, ch, stem, bar):
    """Every stage of one letter, as in render_font."""
    out = {}
    out['outline'] = mono(path_plain, grid, ch, False)[0]
    out['warped'] = mono(path_warped, grid, ch, False)[0]
    rows, cover = mono(path_warped, grid, ch, True)
    out['hinted'] = rows
    name = imp['names'][ord(ch)]
    lr, tb = name in imp['SYM_LR'], name in imp['SYM_TB']
    out['thin only'] = imp['thin'](rows, cover, k=stem, h=bar)
    if lr or tb:
        orig = cover
        r1, c1, orbit = imp['symmetrize'](rows, cover, lr, tb, orig)
        out['mirror'] = r1
        r2 = imp['thin'](r1, c1, k=stem, h=bar, orbit=orbit)
        out['thinned'] = r2
        r3, c3, orbit = imp['symmetrize'](r2, c1, lr, tb, orig)
        r4 = imp['thin'](r3, c3, k=stem, h=bar, orbit=orbit)
        m1, mc, _ = imp['symmetrize'](rows, cover, lr, tb, orig)
        out['mirror only'] = imp['symmetrize'](m1, mc, lr, tb, orig)[0]
    else:
        out['mirror'] = rows
        r4 = out['thinned'] = out['thin only']
        out['mirror only'] = rows
        orbit, c3 = None, cover
    if imp['pieces'](r4) > 1:
        big = freetype.Face(path_warped)
        big.set_pixel_sizes(0, grid * 4)
        want = imp['outline_pieces'](big, ord(ch))
        if imp['pieces'](r4) > want:
            r4 = imp['bridge'](r4, c3, want, orbit)
    out['final'] = r4
    return out


def main():
    grids = [int(g) for g in mine.grids.split(',')]
    tmp = tempfile.mkdtemp()
    tot = {s: collections.Counter() for s in STAGES}
    by_w = {(s, w): collections.Counter() for s in STAGES for w in lib.WEIGHTS}
    same = differ = 0
    odd = []
    dump = mine.dump.split(':') if mine.dump else None
    for grid in grids:
        opsz = min(32, max(14, grid))
        d = imp['measure'](opsz)
        m = imp['grid_metrics'](grid, d)
        pts = imp['warp_map'](grid, m, d)
        unit = imp['UPM'] / grid
        s_reg = max(1, round(imp['ratio']['regular'] * grid))
        targets = {'light': max(1, round(imp['ratio']['light'] * grid)), 'regular': s_reg,
                   'bold': max(s_reg + 1, round(imp['ratio']['bold'] * grid))}
        for weight in lib.WEIGHTS:
            px = targets[weight]
            wght = imp['weight_for_stem'](px * unit, opsz)
            smear = max(0, px - round(imp['stem_of'](imp['instance'](opsz, 900)) / unit)) if wght == 900.0 else 0
            font = imp['instance'](opsz, wght)
            plain = os.path.join(tmp, f'plain-{grid}-{weight}.ttf')
            font.save(plain)
            imp['warp_font'](font, pts)
            warped = os.path.join(tmp, f'warped-{grid}-{weight}.ttf')
            font.save(warped)
            bar = imp['bar_thickness'](imp['bitmap_rows_of_H'](warped, grid))
            meta, G = lib.load(grid, weight)
            for ch in CHARS:
                st = trace(plain, warped, grid, ch, px - smear, bar)
                for s in STAGES:
                    t = measure.tally(measure.score(to_bm(st[s]), px - smear))
                    t['drawings'] += 1
                    t['bent drawings'] += t['bent'] > 0
                    tot[s].update(t)
                    by_w[(s, weight)].update(t)
                fin = st['final']
                if smear:
                    fin = [''.join('#' if any(line[i - k] == '#' for k in range(0, smear + 1) if 0 <= i - k < len(line)) else '.'
                                   for i in range(len(line) + smear)) for line in fin]
                a, b = lib.crop(to_bm(fin)), lib.crop(G[ch]['bm'])
                if a.shape == b.shape and (a == b).all():
                    same += 1
                else:
                    differ += 1
                    odd.append(f'{ch} {grid} {weight}')
                if dump and dump[0] == ch and int(dump[1]) == grid and dump[2] == weight:
                    for s in STAGES:
                        print(f'--- {s}')
                        print('\n'.join(st[s]))
        print(f'grid {grid} done', file=sys.stderr, flush=True)
    print(f'Stage trace, letters {CHARS}, grids {mine.grids}, three weights')
    print(f'final stage equals the committed drawing: {same} of {same + differ}' + (f' (differ: {", ".join(odd)})' if odd else ''))
    print()
    print(f"{'':<14}{'edges':>6}{'bent':>6}{'':>8}{'excess':>8}{'kinks':>7}{'uneven':>8}{'back':>6}{'thin':>6}   drawings with a bent edge")
    for s in STAGES:
        print(measure.line(s, tot[s]) + f"   {tot[s]['bent drawings']} of {tot[s]['drawings']}")
    for w in lib.WEIGHTS:
        print(f'\n{w}')
        for s in STAGES:
            print(measure.line(s, by_w[(s, w)]) + f"   {by_w[(s, w)]['bent drawings']} of {by_w[(s, w)]['drawings']}")


if __name__ == '__main__':
    main()
