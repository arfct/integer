# Integer Sans

Integer Sans is Inter on a pixel grid, in which every value is a whole number: every rendered instance is a real bitmap. The size axis holds a drawing for every grid from 8 to 24 rows and the browser picks one from the font-size, never an interpolation; larger sizes that are a whole multiple of a grid (26 to 48) reuse its drawing at a whole scale. The weight axis steps between Light, Regular, and Bold, each a whole number of pixels of stem. The drawings are rendered from Inter 4.1 by a reproducible pipeline and corrected by hand in override files.

Specimen: https://arfct.github.io/integer/ (built from `main` by the Pages workflow). The design, its reasoning, and the roadmap are in [docs/design.md](docs/design.md).

## Build

```bash
uv venv && uv pip install 'fonttools[woff]' pillow freetype-py
.venv/bin/python scripts/import-inter.py   # renders glyphs/<grid>/<weight>.txt from vendor/inter (about 20 s)
.venv/bin/python scripts/build.py          # build/IntegerSans-VF.ttf and .woff2
.venv/bin/python scripts/check.py          # unhinted FreeType render of every size: no gray, ink matches source, crossbars present (5 min)
```

The importer fixes each grid's rows for x-height, cap height, ascender, and descender from Inter's proportions, picks for each weight the Inter weight whose stem is exactly the target number of pixels, warps the outlines so the metric lines land on those rows, lets FreeType's autohinter snap the stems, erodes curves and diagonals to pixel-perfect strokes of the stem's thickness (vertical) and the bar's (horizontal) using the grayscale coverage as a guide, and mirrors the letters Inter draws symmetric so both sides take the same staircase. Hand fixes go in `glyphs/<grid>/<weight>.overrides.txt`, which the build applies on top and the importer never touches.

## Use

```css
@font-face { font-family: "Integer Sans"; src: url(IntegerSans-VF.woff2); font-weight: 400 700; }
.pixel { font-family: "Integer Sans"; -webkit-font-smoothing: none; }
```

Every whole font-size from 8 to 24 is exact at 1×, and so is every size from 26 to 48 that is a multiple of a grid; at 2× every whole size from 8 to 48 with a drawing is exact. Sizes with no drawing (25, 29, 31, 35, 37, 41, 43, 47) resample the nearest smaller one. Leave `font-optical-sizing` at its default (`auto`) so the size picks the drawing. `font-weight` 200, 400, and 700 or 800 give Light, Regular, and Bold; Light equals Regular below 23px, where both are one pixel.

## Preview

Serve the repo root (`python3 -m http.server`) and open `preview/`: every size from 8 to 48 with the drawing it uses and whether it lands on whole device pixels at your display's density. `build/proof.png` is the same ladder rendered through FreeType and magnified 3×.

## Sources

`glyphs/<grid>/{light,regular,bold}.txt` are generated from `vendor/inter/InterVariable.ttf` (Inter 4.1, SIL Open Font License 1.1) and committed so every build is reproducible. Each file names its grid, ascent, descent, cap height, and x-height in a header; each entry is a name, codepoint, an advance in pixels, an optional `left` offset, and a bitmap (`#` ink, `.` clear). `charset.txt` lists the codepoints to render.

## License

The font is a derivative of Inter and is licensed under the SIL Open Font License 1.1 ([vendor/inter/LICENSE.txt](vendor/inter/LICENSE.txt)); the scripts and everything else in the repo are MIT ([LICENSE](LICENSE)).
