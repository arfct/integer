# CLAUDE.md

This repo follows the Artifact Primer: https://github.com/arfct/ops/tree/main/primer

## This repo

Integer, a variable pixel font in which every instance is a real bitmap. `glyphs/<grid>/{regular,bold}.txt` are the source: one text bitmap per glyph per grid (8, 9, 10, 11, 12, 14, 16 rows per em; `#` ink, `.` clear; header gives the ascent). `scripts/build.py` turns runs of ink into rectangles, pads glyphs to a common rectangle count, and builds one variable font whose `opsz` and `wght` axes step between drawings (steep `avar` maps, neighbour-bounded gvar tents) so nothing ever interpolates; multiples of a grid are duplicate masters. `scripts/check.py` renders every exact size through FreeType and fails on any gray pixel; run it after every build. `scripts/derive.py` regenerates the in-between grids and overwrites, so never run it on a hand-edited grid. `preview/index.html` is the specimen. Setup: `uv venv && uv pip install 'fonttools[woff]' pillow`. Keep every size in whole pixels; the 8- and 16-row metrics are System Six's. `experiments/` holds the earlier continuous build and the size and stepping tests. Read `docs/design.md` before changing the model.
