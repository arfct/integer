"""Audit the committed drawings for the things a pixel-font designer gets
right by hand: clean staircases, no stray pixels, symmetry, shared parts,
aligned zones, one stem and one bar per size, and smooth progress across sizes.

    .venv/bin/python experiments/hand-drawn/audit.py            # table for every grid and weight
    .venv/bin/python experiments/hand-drawn/audit.py --refs     # add the hand-drawn reference columns
    .venv/bin/python experiments/hand-drawn/audit.py --json out/audit.json
    .venv/bin/python experiments/hand-drawn/audit.py --count 'pairs differing'   # one number, for a test
    .venv/bin/python experiments/hand-drawn/audit.py --root DIR  # audit DIR/<grid>/<weight>.txt instead of glyphs/

Reads glyphs/<grid>/<weight>.txt (overrides applied) and nothing else. The
reference columns need experiments/hand-drawn/fetch_refs.py to have run; they
are hand-tuned bitmap strikes of a grotesque sans (X11 75dpi, 8 to 24 px) and
the hand-drawn pixel face already in experiments/pixel-operator. They say
what the same measure reads on drawings a person made, so a count is a defect
rate and not just a number.

Every measure is defined in the function that computes it. All counts are
over printable ASCII (94 glyphs) unless the row says Latin-1.
"""
import argparse
import collections
import json
import os
import sys
import unicodedata

import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ASCII = [chr(c) for c in range(0x21, 0x7F)]
INFLECTED = set('sS$235689?&~@%a{}#')      # outlines with an inflection or a crossing: a reversal there is drawn, not a defect
ROUND = 'oO0cCDbdpq'                        # only convex arcs and straight stems
DIAG = 'vwxzkAVWXYKMNZ/\\'                  # straight diagonals
SYM_LR = 'AHIMOTUVWXYovwx08'
SYM_TB = 'HIOXox0'
ROT = 'NZzSs'
EIGHT = np.ones((3, 3), dtype=bool)


# --- fonts as one shape -----------------------------------------------------
def integer_font(grid, weight, root=None):
    meta, glyphs = lib.load(grid, weight, root)
    G = {}
    for g in glyphs.values():
        for u in g['unicode']:
            G[chr(u)] = {'bm': g['bm'], 'adv': g['advance'], 'left': g['left']}
    return finish({'label': f'{grid} {weight}', 'grid': grid, 'weight': weight, 'base': meta['ascent'],
                   'G': G, 'head_k': meta['stem'], 'head_h': meta['bar'], 'smear': meta['smear']})


def bdf_font(path, label, weight):
    G, asc, size = {}, 0, 0
    lines = open(path, encoding='latin-1').read().split('\n')
    for l in lines:
        if l.startswith('FONT_ASCENT'):
            asc = int(l.split()[1])
        if l.startswith('FONT_DESCENT'):
            desc = int(l.split()[1])
        if l.startswith('PIXEL_SIZE'):
            size = int(l.split()[1])
    i = 0
    while i < len(lines):
        if lines[i].startswith('STARTCHAR'):
            enc = adv = None
            while not lines[i].startswith('BITMAP'):
                p = lines[i].split()
                if p[0] == 'ENCODING':
                    enc = int(p[1])
                elif p[0] == 'DWIDTH':
                    adv = int(p[1])
                elif p[0] == 'BBX':
                    w, h, ox, oy = map(int, p[1:5])
                i += 1
            rows = []
            i += 1
            while not lines[i].startswith('ENDCHAR'):
                bits = bin(int(lines[i], 16))[2:].zfill(len(lines[i]) * 4)
                rows.append([c == '1' for c in bits[:w]])
                i += 1
            if enc is not None and 0x20 < enc < 0x100 and w and h:
                top = asc + 8 - (oy + h)                 # 8 spare rows above the ascent for accents
                bm = np.zeros((asc + desc + 16, max(w, 1)), dtype=bool)
                if 0 <= top and top + h <= bm.shape[0]:
                    bm[top:top + h, :w] = np.array(rows, dtype=bool).reshape(h, w)
                    G[chr(enc)] = {'bm': bm, 'adv': adv, 'left': ox}
        i += 1
    return finish({'label': label, 'grid': size, 'weight': weight, 'base': asc + 8, 'G': G})


def finish(F):
    """Measure the size's own parameters from its drawings: x and cap rows, stem k, bar h."""
    G = F['G']
    for c, g in G.items():
        g['box'] = lib.ink_box(g['bm'])
    F['xtop'] = G['x']['box'][0]
    F['captop'] = G['H']['box'][0]
    F['x'] = F['base'] - F['xtop']
    F['cap'] = F['base'] - F['captop']
    lb = lib.crop(G['l']['bm'])
    F['k'] = int(collections.Counter(int(r.sum()) for r in lb).most_common(1)[0][0])
    hb = lib.crop(G['H']['bm'])
    F['h'] = max(1, int(hb[:, hb.shape[1] // 2].sum()))
    return F


# --- contours ---------------------------------------------------------------
def loops(bm):
    """The outline of the ink as closed loops of runs (x, y, dx, dy, length),
    ink on the right-hand side, diagonal neighbours treated as joined."""
    H, W = bm.shape
    out = collections.defaultdict(list)
    for y, x in zip(*np.where(bm)):
        y, x = int(y), int(x)
        if y == 0 or not bm[y - 1, x]:
            out[(x, y)].append(((x + 1, y), (y, x)))
        if x == W - 1 or not bm[y, x + 1]:
            out[(x + 1, y)].append(((x + 1, y + 1), (y, x)))
        if y == H - 1 or not bm[y + 1, x]:
            out[(x + 1, y + 1)].append(((x, y + 1), (y, x)))
        if x == 0 or not bm[y, x - 1]:
            out[(x, y + 1)].append(((x, y), (y, x)))
    result = []
    while True:
        start = next((v for v, es in out.items() if es), None)
        if start is None:
            break
        v, pix, pts = start, None, [start]
        while True:
            es = out[v]
            e = next((e for e in es if e[1] != pix), es[0]) if len(es) > 1 else es[0]
            es.remove(e)
            v, pix = e
            pts.append(v)
            if v == start and not out[v]:
                break
            if v == start and pix is not None and all(e2[1] == pix for e2 in out[v]):
                break
        runs = []
        for a, b in zip(pts, pts[1:]):
            d = (b[0] - a[0], b[1] - a[1])
            if runs and (runs[-1][2], runs[-1][3]) == d:
                runs[-1][4] += 1
            else:
                runs.append([a[0], a[1], d[0], d[1], 1])
        if len(runs) > 1 and (runs[0][2], runs[0][3]) == (runs[-1][2], runs[-1][3]):
            runs[0][0], runs[0][1] = runs[-1][0], runs[-1][1]
            runs[0][4] += runs[-1][4]
            runs.pop()
        result.append([tuple(r) for r in runs])
    return result


def run_pixels(r):
    """The ink pixels (y, x) that lie along a run."""
    x, y, dx, dy, n = r
    if dx == 1:
        return [(y, x + i) for i in range(n)]
    if dx == -1:
        return [(y - 1, x - 1 - i) for i in range(n)]
    if dy == 1:
        return [(y + i, x - 1) for i in range(n)]
    return [(y - 1 - i, x) for i in range(n)]


def staircases(bm):
    """Per outline loop: the convex/concave turn after each run, and the
    staircase sections, maximal chains of runs whose two ends turn opposite
    ways. A flat at the top of a bowl, a stroke end and a stem side all turn
    the same way at both ends, so they bound sections and are not in them.
    Returns (sections, caps): sections are lists of runs; caps are
    (run, kind, prev_len, next_len) for the same-turn runs."""
    sections, caps = [], []
    for runs in loops(bm):
        n = len(runs)
        if n < 4:
            continue
        turn = [runs[i][2] * runs[(i + 1) % n][3] - runs[i][3] * runs[(i + 1) % n][2] > 0 for i in range(n)]
        step = [turn[i - 1] != turn[i] for i in range(n)]
        for i in range(n):
            if not step[i]:
                caps.append((runs[i], 'out' if turn[i] else 'in', runs[i - 1][4], runs[(i + 1) % n][4]))
        if all(step):
            sections.append(list(runs))
            continue
        s = next(i for i in range(n) if not step[i])
        cur = []
        for j in range(1, n + 1):
            i = (s + j) % n
            if step[i]:
                cur.append(runs[i])
            elif cur:
                sections.append(cur)
                cur = []
    return sections, caps


def reversals(seq, hard):
    """Indices of strict local extrema in a run-length sequence. Hard: both
    neighbours differ by 2 or more (1-3-1), which no straight line and no
    convex arc produces."""
    out = []
    for i in range(1, len(seq) - 1):
        a, b, c = seq[i - 1], seq[i], seq[i + 1]
        if (b - a) * (b - c) > 0 and (not hard or min(abs(b - a), abs(b - c)) >= 2):
            out.append(i)
    return out


def jaggies(bm, ch):
    """(hard kinks, wobbles on round glyphs, uneven diagonals, marks)."""
    marks = np.zeros(bm.shape, dtype=bool)
    hard = wobble = uneven = 0
    sections, _ = staircases(bm)
    for sec in sections:
        hs = [r for r in sec if r[2]]
        vs = [r for r in sec if r[3]]
        for part in (hs, vs):
            lens = [r[4] for r in part]
            for i in reversals(lens, True):
                hard += 1
                for y, x in run_pixels(part[i]):
                    marks[y, x] = True
            if ch in ROUND:
                soft = [i for i in reversals(lens, False)]
                wobble += len(soft)
        if ch in DIAG:
            major = hs if sum(r[4] for r in hs) >= sum(r[4] for r in vs) else vs
            lens = [r[4] for r in major]
            if len(lens) >= 3 and max(lens) - min(lens) >= 2:
                uneven += 1
    return hard, wobble, uneven, marks


def pimples(bm):
    """One-pixel bumps and one-pixel dents: a run of length 1 turning the
    same way at both ends, with both neighbours of length 1."""
    _, caps = staircases(bm)
    marks = np.zeros(bm.shape, dtype=bool)
    out = inn = 0
    for r, kind, a, b in caps:
        if r[4] == 1 and a == 1 and b == 1:
            if kind == 'out':
                out += 1
                for y, x in run_pixels(r):
                    marks[y, x] = True
            else:
                inn += 1
    return out, inn, marks


def blobs(bm, k, h):
    """Ink pixels at the centre of a solid square wider than any stroke."""
    d = ndimage.distance_transform_cdt(np.pad(bm, 1), metric='chessboard')[1:-1, 1:-1]
    return (2 * d - 1) > max(k, h)


def orphans(bm):
    """Ink pixels with no orthogonal neighbour."""
    p = np.pad(bm, 1)
    n4 = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return bm & ~n4


def topology(bm):
    """(ink components, enclosed counters); ink is 8-connected, paper 4-connected."""
    comps = ndimage.label(bm, structure=EIGHT)[1]
    bg, n = ndimage.label(~np.pad(bm, 1))
    return comps, n - 1


def xor(a, b):
    """Differing pixels between two ink-cropped bitmaps, or None when their boxes differ."""
    if a.shape != b.shape:
        return None
    return int((a ^ b).sum())


def band(F, ch, top, bottom=None):
    """The ink of a glyph between two rows (default: to the baseline), cropped to its columns."""
    g = F['G'].get(ch)
    if g is None:
        return None
    b = g['bm'][top:(F['base'] if bottom is None else bottom)]
    return lib.crop(b)


def corner(b, right=False, bottom=False):
    """A bowl's corner as the indent of each row from the extreme inward, until it reaches the side."""
    if b is None or not b.size:
        return None
    if right:
        b = b[:, ::-1]
    if bottom:
        b = b[::-1]
    sig = []
    for r in b:
        i = int(np.argmax(r)) if r.any() else b.shape[1]
        if i == 0:
            break
        sig.append(i)
    return tuple(sig)


def stem_first(b, right=False):
    """Mode of the first (or last) run's length over the middle half of the rows."""
    if b is None or b.shape[0] < 2:
        return None
    rows = b[b.shape[0] // 4: max(b.shape[0] // 4 + 1, b.shape[0] - b.shape[0] // 4)]
    out = []
    for r in rows:
        r = r[::-1] if right else r
        if not r.any():
            continue
        i = int(np.argmax(r))
        j = i
        while j < len(r) and r[j]:
            j += 1
        out.append(j - i)
    return collections.Counter(out).most_common(1)[0][0] if out else None


def bars(b):
    """Thicknesses of the horizontal bars: groups of rows whose longest run spans 3/4 of the ink."""
    out, cur = [], 0
    for r in b:
        best = run = 0
        for v in r:
            run = run + 1 if v else 0
            best = max(best, run)
        if best >= 0.75 * b.shape[1]:
            cur += 1
        elif cur:
            out.append(cur)
            cur = 0
    if cur:
        out.append(cur)
    return out


def dot_boxes(F):
    """(w, h) of the dots a size draws: period, colon, semicolon, i, j, !, ?."""
    out = {}
    for ch, pick in (('.', 0), (':', 0), (';', 0), ('i', 0), ('j', 0), ('!', -1), ('?', -1)):
        g = F['G'].get(ch)
        if g is None:
            continue
        lab, n = ndimage.label(g['bm'], structure=EIGHT)
        if n < 1 or (ch in ':;ij!?' and n < 2):
            out[ch] = None                               # the dot has merged with the rest
            continue
        boxes = sorted(ndimage.find_objects(lab), key=lambda s: s[0].start)
        s = boxes[pick]
        out[ch] = (s[1].stop - s[1].start, s[0].stop - s[0].start)
    return out


def bearing(F, ch):
    g = F['G'].get(ch)
    if g is None or g['box'] is None:
        return None
    y0, y1, x0, x1 = g['box']
    lsb = int(x0) + g['left']
    w = int(x1 - x0) + 1
    return lsb, w, g['adv'] - lsb - w


CLASSES = {
    'lc stem left': ('bhklmnpr', 0), 'lc stem right': ('dhmnqu', 2), 'lc round left': ('cdegoq', 0),
    'lc round right': ('bop', 2), 'uc stem left': ('BDEFHKLMNPR', 0), 'uc round left': ('CGOQ', 0),
    'uc round right': ('DOQ', 2),
}


def audit_font(F):
    """Every per-size measure for one font. Returns a dict of counts and a dict of per-glyph detail."""
    G, k, h = F['G'], F['k'], F['h']
    R = collections.Counter()
    D = collections.defaultdict(dict)
    chars = [c for c in ASCII if c in G and G[c]['box'] is not None]
    R['glyphs'] = len(chars)
    for ch in chars:
        bm = G[ch]['bm']
        hard, wob, unev, marks = jaggies(bm, ch)
        if ch not in INFLECTED:
            R['kinks'] += hard
            R['kink glyphs'] += hard > 0
            if hard:
                D[ch]['kinks'] = hard
        R['kinks incl. inflected'] += hard
        R['round wobbles'] += wob
        R['round wobble glyphs'] += wob > 0
        R['round glyphs'] += ch in ROUND
        R['uneven diagonals'] += unev
        R['uneven diagonal glyphs'] += unev > 0
        R['diagonal glyphs'] += ch in DIAG
        if wob:
            D[ch]['wobbles'] = wob
        if unev:
            D[ch]['uneven'] = unev
        po, pi, _ = pimples(bm)
        R['pimples'] += po
        R['pits'] += pi
        if po:
            D[ch]['pimples'] = po
        nb = int(blobs(bm, k, h).sum())
        R['blob glyphs'] += nb > 0
        if nb:
            D[ch]['blob'] = nb
        if k >= 2:
            no = int(orphans(bm).sum())
            R['orphans (k>=2)'] += no
            if no:
                D[ch]['orphans'] = no
            R['glyphs (k>=2)'] += 1
    # symmetry
    for ch in SYM_LR:
        if ch in G:
            b = lib.crop(G[ch]['bm'])
            n = int((b ^ b[:, ::-1]).sum()) // 2
            R['lr asymmetric glyphs'] += n > 0
            R['lr expected'] += 1
            if n:
                D[ch]['lr'] = n
            lsb, w, rsb = bearing(F, ch)
            R['off centre by 1'] += abs(lsb - rsb) == 1
            R['off centre by 2+'] += abs(lsb - rsb) >= 2
            if lsb != rsb:
                D[ch]['centre'] = (lsb, w, rsb)
    for ch in SYM_TB:
        if ch in G:
            b = lib.crop(G[ch]['bm'])
            n = int((b ^ b[::-1]).sum()) // 2
            R['tb asymmetric glyphs'] += n > 0
            R['tb expected'] += 1
            if n:
                D[ch]['tb'] = n
    for ch in ROT:
        if ch in G:
            b = lib.crop(G[ch]['bm'])
            n = int((b ^ b[::-1, ::-1]).sum()) // 2
            R['rot asymmetric ' + ('NZz' if ch in 'NZz' else 'Ss')] += n > 0
            if n:
                D[ch]['rot'] = n
    # shared parts, inside the x band
    xb = {c: band(F, c, F['xtop']) for c in 'bdpqnhuoceg'}
    whole = {c: lib.crop(G[c]['bm']) for c in 'nu' if c in G}     # n and u may overshoot the band, on opposite sides
    pairs = [('b', 'd', lambda a: a[:, ::-1]), ('p', 'q', lambda a: a[:, ::-1]), ('b', 'q', lambda a: a[::-1, ::-1]),
             ('d', 'p', lambda a: a[::-1, ::-1]), ('n', 'u', lambda a: a[::-1, ::-1]), ('n', 'h', lambda a: a)]
    for a, b, f in pairs:
        if xb.get(a) is None or xb.get(b) is None:
            continue
        n = xor(whole[a], f(whole[b])) if (a, b) == ('n', 'u') else xor(xb[a], f(xb[b]))
        key = f'{a} vs {b}'
        R['pair ' + key] += n != 0
        R['pairs differing'] += n != 0
        R['pairs'] += 1
        if n != 0:
            D[a + b]['pair'] = 'box' if n is None else n
    tops = {c: corner(xb[c]) for c in 'ocedqg'}
    tops.update({c + "'": corner(xb[c], right=True) for c in 'obp'})
    bots = {c: corner(xb[c], bottom=True) for c in 'ocedq'}
    bots.update({c + "'": corner(xb[c], right=True, bottom=True) for c in 'obp'})
    F['corners'] = {'top': tops, 'bottom': bots}
    R['corner templates top'] = len(set(tops.values()))
    R['corner templates bottom'] = len(set(bots.values()))
    R['corner sets not shared'] = (len(set(tops.values())) > 1) + (len(set(bots.values())) > 1)
    cb = {c: band(F, c, F['captop']) for c in 'OCGQ'}
    ctop = {c: corner(cb[c]) for c in 'OCGQ'}
    R['cap corner templates top'] = len(set(ctop.values()))
    # accented letters reuse their base (Latin-1)
    for cp in range(0xC0, 0x100):
        ch = chr(cp)
        nfd = unicodedata.normalize('NFD', ch)
        if len(nfd) != 2 or ch not in G or nfd[0] not in G or nfd[0] in 'ij':
            continue
        base = nfd[0]
        top = F['captop'] if base.isupper() else F['xtop']
        bottom = F['base'] if nfd[1] == '\u0327' or base.isupper() else F['bm_rows'] if False else None
        if base in 'y':
            bottom = G[base]['bm'].shape[0]
        a = band(F, base, top, bottom if bottom else F['base'])
        b = band(F, ch, top, bottom if bottom else F['base'])
        n = xor(a, b)
        R['accented'] += 1
        R['accented base differs'] += n != 0
        R['accented advance differs'] += G[ch]['adv'] != G[base]['adv']
        if n != 0:
            D[ch]['base'] = 'box' if n is None else n
    # zones: every group of like glyphs sits on one row (round groups may overshoot, but together)
    def top_of(c):
        return int(G[c]['box'][0])

    def bottom_of(c):
        return int(G[c]['box'][1]) + 1

    groups = [('x top flat', 'uvwxz', top_of), ('x top round', 'aceos', top_of), ('x top arch', 'mnr', top_of),
              ('cap top flat', 'BDEFHIKLMNPRTUVWXYZ', top_of), ('cap top round', 'CGOQS', top_of),
              ('figure top flat', '1457', top_of), ('figure top round', '023689', top_of),
              ('ascender', 'bdhkl', top_of), ('descender', 'gpqy', bottom_of),
              ('baseline flat', 'fhiklmnrxzAEFHIKLMNPRTXZ1247', bottom_of),
              ('baseline round', 'abcdeostuCGOSU035689', bottom_of)]
    for name, members, f in groups:
        vals = collections.Counter(f(c) for c in members if c in G)
        mode = vals.most_common(1)[0][0]
        for c in members:
            if c in G and f(c) != mode:
                R['zone misses'] += 1
                D[c]['zone'] = name
    R['zone glyphs'] += sum(len(m) for _, m, _ in groups)
    R['overshoots'] = int(top_of('o') < F['xtop'])
    # drawings cut off at the left edge of their box: the importer drops the columns left of the
    # origin and then writes the offset as well, so a negative offset with ink on column 0 is a cut
    for ch in G:
        g = G[ch]
        if g['left'] < 0 and 'head_k' in F:
            R['negative left'] += 1
            R['negative left, ink on the box edge'] += bool(g['bm'][:, 0].any())
    R['all glyphs'] = len(G)
    # dots
    dots = dot_boxes(F)
    F['dots'] = dots
    R['dot sizes'] = len(set(dots.values()))
    R['dots merged'] = sum(1 for v in dots.values() if v is None)
    # stems and bars
    for c in 'bhklmnpr' + 'BDEFHKLMNPR':
        s = stem_first(lib.crop(G[c]['bm'])) if c in G else None
        if s is not None:
            R['stems measured'] += 1
            if s != k:
                R['stems off'] += 1
                D[c]['stem'] = s
    for c in 'dqu':
        s = stem_first(lib.crop(G[c]['bm']), right=True) if c in G else None
        if s is not None:
            R['stems measured'] += 1
            if s != k:
                R['stems off'] += 1
                D[c]['stem'] = s
    for c in 'EFHLTZzft':
        if c in G:
            for t in bars(lib.crop(G[c]['bm'])):
                R['bars measured'] += 1
                if t != h:
                    R['bars off'] += 1
                    D[c]['bar'] = t
    # spacing by class
    F['bearings'] = {}
    for name, (members, side) in CLASSES.items():
        vals = [bearing(F, c)[side] for c in members if c in G]
        F['bearings'][name] = vals
        spread = max(vals) - min(vals)
        R['bearing classes'] += 1
        R['bearing classes split'] += spread > 0
        R['bearing spread px'] += spread
    return R, D


# --- across sizes and weights (Integer only) --------------------------------
def cross_size(fonts):
    """fonts: {(grid, weight): F}. Counts of steps n -> n+1 where a glyph gets
    narrower, shorter, lighter or simpler, and of parameter reversals."""
    R = collections.Counter()
    detail = collections.defaultdict(list)
    grids = sorted({g for g, _ in fonts})
    for w in lib.WEIGHTS:
        seq = [fonts[(g, w)] for g in grids if (g, w) in fonts]
        ref_top = {}
        for c in ASCII:
            big = [topology(F['G'][c]['bm']) for F in seq if F['grid'] >= 25 and c in F['G']] or \
                  [topology(F['G'][c]['bm']) for F in seq if c in F['G']]
            ref_top[c] = (collections.Counter(t[0] for t in big).most_common(1)[0][0],
                          collections.Counter(t[1] for t in big).most_common(1)[0][0])
        for key in ('k', 'h', 'x', 'cap'):
            vals = [F[key] for F in seq]
            for a, b, F in zip(vals, vals[1:], seq[1:]):
                if b < a:
                    R[f'{key} decreases'] += 1
                    detail[f'{key} decreases'].append(f"{w} {F['grid'] - 1}->{F['grid']}: {a}->{b}")
        for ch in ASCII:
            prev = None
            for F in seq:
                g = F['G'].get(ch)
                if g is None or g['box'] is None:
                    continue
                lsb, wid, rsb = bearing(F, ch)
                y0, y1 = g['box'][0], g['box'][1]
                cur = dict(adv=g['adv'], width=wid, height=int(y1 - y0 + 1), ink=int(g['bm'].sum()), lsb=lsb, rsb=rsb)
                top = topology(g['bm'])
                R['glyph sizes'] += 1
                for i, (more, fewer) in enumerate((('broken: more ink pieces than the large sizes', 'merged: fewer ink pieces'),
                                                   ('extra counters', 'closed counters'))):
                    if top[i] != ref_top[ch][i]:
                        key = more if top[i] > ref_top[ch][i] else fewer
                        R[key] += 1
                        detail[key].append(f"{ch} {F['label']}: {top[i]} vs {ref_top[ch][i]}")
                if prev:
                    R['steps'] += 1
                    for key in ('adv', 'width', 'height', 'ink'):
                        if cur[key] < prev[key]:
                            R[f'{key} decreases'] += 1
                            detail[f'{key} decreases'].append(f"{ch} {w} {F['grid'] - 1}->{F['grid']}: {prev[key]}->{cur[key]}")
                    for key in ('lsb', 'rsb'):
                        if cur[key] < prev[key]:
                            R['bearing decreases'] += 1
                            detail['bearing decreases'].append(f"{ch} {w} {key} {F['grid'] - 1}->{F['grid']}: {prev[key]}->{cur[key]}")
                prev = cur
    # weights
    for g in grids:
        L, Rg, B = (fonts.get((g, w)) for w in lib.WEIGHTS)
        if not (L and Rg and B):
            continue
        R['sizes'] += 1
        same = all(np.array_equal(L['G'][c]['bm'], Rg['G'][c]['bm']) for c in ASCII if c in L['G'])
        R['sizes where light is regular'] += same
        if B['k'] - Rg['k'] != 1:
            detail['bold step'].append(f"{g}: regular {Rg['k']} bold {B['k']}")
        R['sizes where bold is exactly one stem step up'] += B['k'] - Rg['k'] == 1
        for c in ASCII:
            if c not in B['G'] or B['G'][c]['box'] is None:
                continue
            R['weight pairs'] += 1
            if B['G'][c]['adv'] < Rg['G'][c]['adv']:
                R['bold narrower advance'] += 1
            if B['G'][c]['bm'].sum() <= Rg['G'][c]['bm'].sum():
                R['bold not heavier'] += 1
                detail['bold not heavier'].append(f'{c} {g}')
            if not same and L['G'][c]['bm'].sum() > Rg['G'][c]['bm'].sum():
                R['light heavier than regular'] += 1
                detail['light heavier'].append(f'{c} {g}')
    return R, detail


# --- report -----------------------------------------------------------------
ROWS = [
    ('glyphs', 'glyph drawings audited', None),
    ('kinks', 'hard staircase kinks (1-3-1)', 'glyphs'),
    ('kink glyphs', '  glyphs with one', 'glyphs'),
    ('round wobble glyphs', 'round glyphs with a non-monotone arc', 'round glyphs'),
    ('uneven diagonal glyphs', 'diagonal glyphs with uneven steps', 'diagonal glyphs'),
    ('pimples', 'one-pixel bumps', 'glyphs'),
    ('pits', 'one-pixel dents', 'glyphs'),
    ('orphans (k>=2)', 'pixels with no orthogonal neighbour, stems 2+', 'glyphs (k>=2)'),
    ('blob glyphs', 'glyphs with a blob wider than the stroke', 'glyphs'),
    ('lr asymmetric glyphs', 'left-right asymmetric (of 17 expected)', 'lr expected'),
    ('off centre by 1', 'symmetric glyph off centre by 1', 'lr expected'),
    ('off centre by 2+', 'symmetric glyph off centre by 2+', 'lr expected'),
    ('tb asymmetric glyphs', 'top-bottom asymmetric (of 7 expected)', 'tb expected'),
    ('rot asymmetric NZz', 'N Z z not point-symmetric', None),
    ('rot asymmetric Ss', 'S s not point-symmetric', None),
    ('pairs differing', 'bowl/arch pairs that differ (6 per size)', 'pairs'),
    ('corner sets not shared', 'corner sets with 2+ templates (2 per size)', None),
    ('accented base differs', 'accented letters whose base differs (Latin-1)', 'accented'),
    ('zone misses', 'glyphs off their group\'s metric row', 'zone glyphs'),
    ('negative left, ink on the box edge', 'drawings clipped at the left edge (Latin-1)', 'all glyphs'),
    ('dots merged', 'dots merged into the letter', None),
    ('stems off', 'stems not the size\'s stem', 'stems measured'),
    ('bars off', 'bars not the size\'s bar', 'bars measured'),
    ('bearing classes split', 'sidebearing classes with 2+ values (7 per size)', 'bearing classes'),
    ('bearing spread px', '  total spread in pixels', None),
]


def table(columns):
    """columns: [(title, Counter)]. Prints count and rate per column."""
    wid = max(len(r[1]) for r in ROWS) + 2
    print(' ' * wid + ''.join(f'{t:>17}' for t, _ in columns))
    for key, label, denom in ROWS:
        line = label.ljust(wid)
        for _, R in columns:
            v = R.get(key, 0)
            if denom and R.get(denom):
                line += f'{v:>9} {100 * v / R[denom]:>6.1f}%'
            else:
                line += f'{v:>9}        '
        print(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refs', action='store_true')
    ap.add_argument('--json')
    ap.add_argument('--grids', default='7-48')
    ap.add_argument('--root', help='a directory laid out like glyphs/, e.g. a spike\'s output')
    ap.add_argument('--count', help='print only this count: a key of the table (see ROWS) or of the across-sizes list')
    opt = ap.parse_args()
    lo, hi = map(int, opt.grids.split('-'))
    fonts, results, details = {}, {}, {}
    for g in range(lo, hi + 1):
        for w in lib.WEIGHTS:
            F = integer_font(g, w, opt.root)
            fonts[(g, w)] = F
            results[(g, w)], details[(g, w)] = audit_font(F)

    def total(keys):
        t = collections.Counter()
        for key in keys:
            t.update(results[key])
        return t

    if opt.count:
        T, (X, _) = total(results), cross_size(fonts)
        hits = [v for k, v in list(T.items()) + list(X.items()) if k == opt.count or k.startswith(opt.count + ':')]
        known = [r[0] for r in ROWS] + ['broken', 'merged', 'extra counters', 'closed counters', 'adv decreases',
                                        'width decreases', 'ink decreases', 'h decreases', 'k decreases']
        if not hits and opt.count not in known:
            sys.exit(f'no such count: {opt.count}')
        print(hits[0] if hits else 0)
        return

    print(f'Integer Sans, grids {lo} to {hi}, printable ASCII; count and rate per column\n')
    print('By weight, all grids')
    table([(w, total([k for k in results if k[1] == w])) for w in lib.WEIGHTS] + [('all', total(results))])
    print('\nBy size band, all weights')
    bands = [('7-12', 7, 12), ('13-16', 13, 16), ('17-24', 17, 24), ('25-48', 25, 48)]
    table([(n, total([k for k in results if a <= k[0] <= b])) for n, a, b in bands])

    refs = {}
    if opt.refs:
        rd = os.path.join(lib.HERE, 'out', 'ref')
        cols = []
        for tag, wname in (('R', 'regular'), ('B', 'bold')):
            t = collections.Counter()
            for size in ('08', '10', '12', '14', '18', '24'):
                p = os.path.join(rd, f'helv{tag}{size}.bdf')
                if os.path.exists(p):
                    F = bdf_font(p, f'ref {int(size)} {wname}', wname)
                    refs[(F['grid'], 'ref-' + wname)] = F
                    R, D = audit_font(F)
                    results_ref = R
                    details[(F['grid'], 'ref-' + wname)] = D
                    t.update(R)
            cols.append((f'hand {wname}', t))
            same = [k for k in results if k[1] == wname and k[0] in (8, 10, 12, 14, 18, 24)]
            cols.append((f'Integer {wname}', total(same)))
        po = collections.Counter()
        for g in (8, 16):
            for w in ('regular', 'bold'):
                p = os.path.join(lib.ROOT, 'experiments', 'pixel-operator', str(g), w + '.txt')
                meta, glyphs = lib.parse(p)
                G = {chr(u): {'bm': gl['bm'], 'adv': gl['advance'], 'left': gl['left']}
                     for gl in glyphs.values() for u in gl['unicode']}
                F = finish({'label': f'po {g} {w}', 'grid': g, 'weight': w, 'base': int(meta['ascent']), 'G': G})
                R, D = audit_font(F)
                po.update(R)
        cols.append(('pixel face', po))
        print('\nAgainst hand-drawn references: the same six sizes (8 10 12 14 18 24), and a hand-drawn pixel face (8, 16; two weights)')
        table(cols)

    X, xd = cross_size(fonts)
    print('\nAcross sizes (each step n -> n+1, per glyph and weight) and weights')
    for key in ('steps', 'adv decreases', 'width decreases', 'height decreases', 'ink decreases', 'bearing decreases',
                'glyph sizes', 'broken: more ink pieces than the large sizes', 'merged: fewer ink pieces',
                'extra counters', 'closed counters',
                'k decreases', 'h decreases', 'x decreases', 'cap decreases',
                'sizes', 'sizes where light is regular', 'sizes where bold is exactly one stem step up',
                'weight pairs', 'bold narrower advance', 'bold not heavier', 'light heavier than regular'):
        print(f'  {key:<48}{X.get(key, 0):>7}')
    for key in ('h decreases', 'k decreases'):
        if xd.get(key):
            print(f'  {key}: ' + '; '.join(xd[key]))
    ratios = ' '.join(f"{g}:{fonts[(g, 'bold')]['k']}/{fonts[(g, 'regular')]['k']}" for g in range(lo, hi + 1))
    print('  bold stem / regular stem by size: ' + ratios)
    for key in ('ink decreases', 'width decreases', 'adv decreases'):
        steps = collections.Counter(d.rsplit(': ', 1)[0].split(' ')[-1] for d in xd.get(key, []))
        print(f'  {key}, the steps with most: ' + ', '.join(f'{s_} ({n})' for s_, n in steps.most_common(6)))
    for name in ('pair b vs d', 'pair p vs q', 'pair b vs q', 'pair d vs p', 'pair n vs u', 'pair n vs h'):
        print(f"  {name[5:]} differ at {sum(R.get(name, 0) for R in results.values())} of {len(results)} drawings")

    print('\nPer size: measured stem k and bar h (light regular bold), corner templates among o c e d q g b p, dot sizes')
    for g in range(lo, hi + 1):
        F = fonts[(g, 'regular')]
        kh = ' '.join(f"{fonts[(g, w)]['k']}/{fonts[(g, w)]['h']}" for w in lib.WEIGHTS)
        tops = collections.Counter(F['corners']['top'].values())
        dots = collections.Counter(F['dots'].values())
        print(f"  {g:>2}  k/h {kh:<14} x {F['x']:>2} cap {F['cap']:>2}  top corners {len(tops)}: "
              + ' '.join(f"{'-'.join(map(str, s)) if s else 'square'}x{n}" for s, n in tops.most_common())
              + '   dots ' + ' '.join(f'{d[0]}x{d[1]}' if d else 'merged' for d in dots))

    if opt.json:
        out = {
            'per_size': {f'{g} {w}': dict(results[(g, w)]) for (g, w) in results},
            'detail': {f'{g} {w}': {c: d for c, d in details[(g, w)].items()} for (g, w) in details},
            'cross': dict(X), 'cross_detail': {k: v for k, v in xd.items()},
            'params': {f'{g} {w}': {key: F[key] for key in ('k', 'h', 'x', 'cap')} for (g, w), F in fonts.items()},
        }
        os.makedirs(os.path.dirname(os.path.abspath(opt.json)), exist_ok=True)
        json.dump(out, open(opt.json, 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
