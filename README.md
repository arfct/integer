# Integer

Integer is a variable pixel font built from text bitmaps, where every rendered instance is a real drawing and every value is a whole number. The size axis is stepped: it holds a drawing per pixel grid (8 and 16 rows today) and the browser picks one from the font-size, never an interpolation. The weight axis steps the same way between 1px and 2px stems. The grids and metrics are those of the System Six faces, so it drops in where Pixel Operator is used today.

The design, its reasoning, and the roadmap are in [docs/design.md](docs/design.md).

## Build

```bash
uv venv && uv pip install 'fonttools[woff]' pillow
.venv/bin/python scripts/build.py     # build/Integer-VF.ttf and .woff2
.venv/bin/python scripts/check.py     # renders every exact size through FreeType; fails on any gray pixel
```

`scripts/derive.py` regenerates the 9, 10, 11, 12, and 14-row sources from the 8- and 16-row ones; it overwrites, so do not run it on grids that have been edited by hand.

## Use

```css
@font-face { font-family: "Integer"; src: url(Integer-VF.woff2); font-weight: 400 700; }
.pixel { font-family: "Integer"; -webkit-font-smoothing: none; }
```

A font-size that is a whole multiple of a grid is exact at 1×; at 2× every whole font-size from 8 up with a drawing is exact. Sizes between drawings resample the nearest smaller one. Leave `font-optical-sizing` at its default (`auto`) so the size picks the drawing.

## Preview

Serve the repo root (`python3 -m http.server`) and open `preview/`: every size from 8 to 48 with the drawing it uses and whether it lands on whole device pixels at your display's density. `build/proof.png` is the same ladder rendered through FreeType and magnified 3×.

## Sources

`glyphs/<grid>/{regular,bold}.txt` are the font. Each file names its grid and ascent in a header; each entry is a name, codepoints, an advance in pixels, and a bitmap (`#` ink, `.` clear). The 8- and 16-row drawings were imported from Pixel Operator and Pixel Operator 8 (Jayvee Enaguas, CC0 1.0) with `scripts/import-pixel-operator.py`; the rest were derived and are meant to be corrected by hand.
