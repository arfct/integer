# CLAUDE.md

This repo follows the Artifact Primer: https://github.com/arfct/ops/tree/main/primer

## This repo

Integer, a variable pixel font built from text bitmaps. `glyphs/*.txt` are the source (one entry per glyph: name, unicode, advance, and a 16-row bitmap, `#` ink and `.` clear, 13 rows above the baseline); `scripts/build.py` turns every pixel into a rectangle contour and builds the variable font with fontTools (`wght` = smear right, `slnt` = row shift, `ROND` = corner radius); `preview/index.html` is the specimen. Build with `.venv/bin/python scripts/build.py` after `uv venv && uv pip install 'fonttools[woff]'`. Outputs in `build/` are not committed. Keep every size in whole pixels; axes must only move or resize rectangles so masters stay compatible. `experiments/stepped/` is the stepped model (one drawing per grid and weight, `avar` steps so no interpolation ever renders); it is the direction and folds into `scripts/build.py` next. Read `docs/design.md` before changing the model.
