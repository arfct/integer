# Integer Sans

Integer Sans is a variable pixel font in which every value is a whole number: every rendered instance is a real drawing on a pixel grid. The size axis holds a drawing per grid (8, 9, 10, 11, 12, 14, and 16 rows) and the browser picks one from the font-size, never an interpolation; multiples of a grid (18, 20, 22, 24, 28, 32, 36, 40, 44, 48) reuse its drawing at a whole scale. The weight axis steps the same way between 1px and 2px stems. The 8- and 16-row grids are the System Six faces; the others are derived from them and open to hand editing.

The design, its reasoning, and the roadmap are in [docs/design.md](docs/design.md).

## Build

```bash
uv venv && uv pip install 'fonttools[woff]' pillow
.venv/bin/python scripts/build.py     # build/IntegerSans-VF.ttf and .woff2
.venv/bin/python scripts/check.py     # renders every exact size through FreeType; fails on any gray pixel
```

`scripts/derive.py` regenerates the 9, 10, 11, 12, and 14-row sources from the 8- and 16-row ones; it overwrites, so do not run it on grids that have been edited by hand.

## Use

```css
@font-face { font-family: "Integer Sans"; src: url(IntegerSans-VF.woff2); font-weight: 400 700; }
.pixel { font-family: "Integer Sans"; -webkit-font-smoothing: none; }
```

A font-size that is a whole multiple of a grid is exact at 1×; at 2× every whole font-size from 8 up with a drawing is exact. Sizes between drawings resample the nearest smaller one. Leave `font-optical-sizing` at its default (`auto`) so the size picks the drawing.

## Preview

Serve the repo root (`python3 -m http.server`) and open `preview/`: every size from 8 to 48 with the drawing it uses and whether it lands on whole device pixels at your display's density. `build/proof.png` is the same ladder rendered through FreeType and magnified 3×.

## Sources

`glyphs/<grid>/{regular,bold}.txt` are the font. Each file names its grid and ascent in a header; each entry is a name, codepoints, an advance in pixels, and a bitmap (`#` ink, `.` clear). The 8- and 16-row drawings were imported from Pixel Operator and Pixel Operator 8 (Jayvee Enaguas, CC0 1.0) with `scripts/import-pixel-operator.py`; the rest were derived and are meant to be corrected by hand.
