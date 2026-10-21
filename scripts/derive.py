"""Derive the in-between grids from the two drawn ones.

    python scripts/derive.py            # writes glyphs/{9,10,11,12,14}/{regular,bold}.txt

9, 10, 11 come from the 8-row drawings: one more descender row, then 0, 1, 2
rows of lead above the caps. 12 and 14 come from the 16-row drawings by
removing lead rows (three for 12, two for 14) and, for 12, one descender row.
Rows are removed where it changes the drawing least: empty rows first, then a
row identical to a neighbour, then a row that is only stems passing through.
Rows are inserted as the overlap of the two rows around the insertion point,
which lengthens stems without thickening bars.

The output files are sources: edit them by hand, and do not re-run this script
on grids that have been edited (it overwrites). Bold gets the same row edits
as Regular, so the two stay aligned.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'glyphs')


def parse(path):
    text = open(path).read()
    meta = dict(re.findall(r'^# (\w+): (\S+)', text, flags=re.M))
    text = re.sub(r'^#.*\n?', '', text, flags=re.M)
    glyphs = []
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = [l for l in block.split('\n') if l]
        if lines[0].startswith('name:'):
            fields = {k.strip(): v.strip() for k, v in (l.split(':', 1) for l in lines)}
            glyphs.append({'name': fields['name'], 'unicode': fields.get('unicode', ''),
                           'advance': int(fields['advance']), 'rows': []})
        else:
            glyphs[-1]['rows'] = lines
    return int(meta['ascent']), glyphs


def write(path, grid, ascent, glyphs, note):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(f'# Integer Sans, {grid}-row grid, {os.path.basename(path)[:-4]}. {note}\n'
                 f'# grid: {grid}\n# ascent: {ascent}\n'
                 '# "#" is ink, "." is clear. Edit freely: this file is the source.\n\n')
        for g in glyphs:
            fh.write(f"name: {g['name']}\nunicode: {g['unicode']}\nadvance: {g['advance']}\n\n"
                     + '\n'.join(g['rows']) + '\n\n')


def ink(row):
    return row.count('#')


def row_and(a, b):
    return ''.join('#' if x == '#' and y == '#' else '.' for x, y in zip(a, b))


def removal_score(rows, i):
    """Lower is safer to remove."""
    r = rows[i]
    if ink(r) == 0:
        return 0
    above = rows[i - 1] if i > 0 else None
    below = rows[i + 1] if i + 1 < len(rows) else None
    if r == above or r == below:
        return 1
    if above and below and r == row_and(above, below):
        return 2
    return 3 + ink(r)


def remove_rows(rows, zone, n):
    """Remove n rows from the row indices in `zone` (top to bottom), safest first.
    Returns (new rows, removed indices in the original numbering)."""
    removed = []
    cur = list(rows)
    live = list(zone)
    for _ in range(n):
        best = min(live, key=lambda i: (removal_score(cur, i - sum(1 for r in removed if r < i)), i))
        removed.append(best)
        live.remove(best)
        del cur[best - sum(1 for r in removed[:-1] if r < best)]
    return cur, removed


def apply_removals(rows, removed):
    return [r for i, r in enumerate(rows) if i not in removed]


def insertion_point(rows, zone_pairs):
    """Pick (i, row) to insert before index i so the drawing grows by one row."""
    best = None
    for i in zone_pairs:                      # insert between rows i-1 and i
        a, b = rows[i - 1], rows[i]
        overlap = row_and(a, b)
        score = ink(overlap)
        if best is None or score >= best[0]:
            best = (score, i, overlap if score else (a if ink(a) <= ink(b) else b))
    return best[1], best[2]


def apply_insertion(rows, i, new_row):
    return rows[:i] + [new_row] + rows[i:]


def derive_small(asc8, reg8, bold8, lead, descent):
    """From the 8-row drawings (ascent 7, descent 1): descent rows and lead rows."""
    out = []
    for g, gb in zip(reg8, bold8):
        rows, brows = list(g['rows']), list(gb['rows'])
        for _ in range(descent - 1):
            bottom = len(rows) - 1
            if ink(rows[bottom]):                          # only glyphs that use the descender
                pairs = [bottom - 1, bottom]               # insert between (x-height..baseline..bottom)
                i, new = insertion_point(rows, pairs)
                rows = apply_insertion(rows, i, new)
                _, newb = insertion_point(brows, [i])
                brows = apply_insertion(brows, i, newb)
            else:
                rows.append('.' * len(rows[0])); brows.append('.' * len(brows[0]))
        blank, blankb = '.' * len(rows[0]), '.' * len(brows[0])
        rows = [blank] * lead + rows
        brows = [blankb] * lead + brows
        out.append(({**g, 'rows': rows}, {**gb, 'rows': brows}))
    return out


def derive_large(asc16, reg16, bold16, lead_remove, desc_remove):
    """From the 16-row drawings (ascent 13, cap 9, descent 3)."""
    out = []
    for g, gb in zip(reg16, bold16):
        rows, brows = list(g['rows']), list(gb['rows'])
        n = len(rows)
        lead_zone = list(range(0, asc16 - 9))                   # rows above the cap height
        rows2, removed = remove_rows(rows, lead_zone, lead_remove)
        brows = apply_removals(brows, removed)
        rows = rows2
        if desc_remove:
            n = len(rows)
            desc_zone = list(range(n - 3, n))                    # the three descender rows
            rows2, removed = remove_rows(rows, desc_zone, desc_remove)
            brows = apply_removals(brows, removed)
            rows = rows2
        out.append(({**g, 'rows': rows}, {**gb, 'rows': brows}))
    return out


asc8, reg8 = parse(os.path.join(ROOT, '8', 'regular.txt'))
_, bold8 = parse(os.path.join(ROOT, '8', 'bold.txt'))
asc16, reg16 = parse(os.path.join(ROOT, '16', 'regular.txt'))
_, bold16 = parse(os.path.join(ROOT, '16', 'bold.txt'))

plan = {
    9: ('small', dict(lead=0, descent=2), asc8),
    10: ('small', dict(lead=1, descent=2), asc8 + 1),
    11: ('small', dict(lead=2, descent=2), asc8 + 2),
    12: ('large', dict(lead_remove=3, desc_remove=1), asc16 - 3),
    14: ('large', dict(lead_remove=2, desc_remove=0), asc16 - 2),
}
only = [int(a) for a in sys.argv[1:]] or list(plan)
for grid in only:
    kind, kw, ascent = plan[grid]
    pairs = derive_small(asc8, reg8, bold8, **kw) if kind == 'small' else derive_large(asc16, reg16, bold16, **kw)
    note = (f'Derived from the 8-row drawings by scripts/derive.py ({kw}).' if kind == 'small'
            else f'Derived from the 16-row drawings by scripts/derive.py ({kw}).')
    write(os.path.join(ROOT, str(grid), 'regular.txt'), grid, ascent, [p[0] for p in pairs], note)
    write(os.path.join(ROOT, str(grid), 'bold.txt'), grid, ascent, [p[1] for p in pairs], note)
    print(f'grid {grid}: ascent {ascent}, descent {grid - ascent}, {len(pairs)} glyphs')
