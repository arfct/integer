# Integer Sans

> **Prototype.** This is a test of a pipeline, not a finished typeface. The character set is Latin-1 only, sizes below 9 are present but not readable, the drawings are machine-rendered and largely uncorrected by hand, there is no kerning, and names, metrics, and the axis layout may change without notice. Do not ship it in anything you cannot update.

Integer Sans is a variable pixel font in which every value is a whole number: every rendered instance is a real bitmap. It ships as two families: **Integer Sans** holds a drawing for every size from 7 to 24 and **Integer Sans Display** one for every size from 25 to 48; the browser picks the drawing from the font-size, never an interpolation. The weight axis steps between Light, Regular, and Bold, each a whole number of pixels of stem. The drawings are rendered from a source typeface by a reproducible pipeline and corrected by hand in override files.

Specimen: https://arfct.github.io/integer/ (built from `main` by the Pages workflow). The importer renders grids 7 to 48 in about six minutes; the files are committed, so builds never need it. The design, its reasoning, and the roadmap are in [docs/design.md](docs/design.md).

## Build

```bash
uv venv && uv pip install 'fonttools[woff]' pillow freetype-py numpy
.venv/bin/python scripts/import-inter.py   # renders glyphs/<grid>/<weight>.txt, grids 7 to 48, from the source typeface (about 6 min; the build does not need it)
.venv/bin/python scripts/build.py          # build/IntegerSans-VF.ttf and .woff2, sizes 7 to 24
.venv/bin/python scripts/build.py --family "Integer Sans Display" --min-size 25 --max-size 48 --default-size 32 --out build/display
.venv/bin/python scripts/check.py          # unhinted FreeType render of every size: no gray, ink matches source, crossbars present
.venv/bin/python scripts/check.py --font build/display/IntegerSansDisplay-VF.ttf --png build/display/proof.png
```

The importer fixes each grid's rows for x-height, cap height, ascender, and descender from the source's proportions, picks for each weight the source instance whose stem is exactly the target number of pixels, warps the outlines so the metric lines land on those rows, lets FreeType's autohinter snap the stems, erodes curves and diagonals to pixel-perfect strokes of the stem's thickness (vertical) and the bar's (horizontal) using the grayscale coverage as a guide, and mirrors the letters the source draws symmetric so both sides take the same staircase. Neither the mirror nor the erosion may split a drawing or lose a piece of it: a mirror pass that would is redone keeping both sides' ink, a group of mirrored pixels that would is kept, and a drawing still in more pieces than its outline has is joined at its best-covered clear pixel. Composite glyphs (the accented letters, `i`, `j`, the comma, the colon) are decomposed before the outlines are warped, so none is warped twice. A last stage derives the letters that share a part from one master: `d` is `b` mirrored, `p` is `b`'s bowl flipped over its own descender, `q` is `p` mirrored, `h` is `n`'s arch on its own stem, `u` is `n` turned, and every accented letter is its base letter's drawing with the accent set over it, a row clear of the letter where the line box has room (`ì í î ï` are `i`'s stem under the accent, on their own advance). The colon is the period twice and the semicolon is the period over the comma, assembled from those two drawings. A rule is skipped at a grid and weight where the source itself draws the pair differently there: at 43 to 48 the top overshoot row survives and the bottom one does not, so `p` is not `b` flipped and `u` is not `n` turned. Hand fixes go in `glyphs/<grid>/<weight>.overrides.txt`, which the build applies on top and the importer never touches; a fix to a master such as `b` does not reach the letters derived from it, so override those as well.

## Use

```css
@font-face { font-family: "Integer Sans"; src: url(IntegerSans-VF.woff2); font-weight: 200 800; }
@font-face { font-family: "Integer Sans Display"; src: url(IntegerSansDisplay-VF.woff2); font-weight: 200 800; }
.pixel { font-family: "Integer Sans"; -webkit-font-smoothing: none; }           /* 7px to 24px */
.pixel-large { font-family: "Integer Sans Display"; -webkit-font-smoothing: none; }  /* 25px to 48px */
```

Every whole font-size from 7 to 48 is exact at 1× with the right family, and at 2× as well. Above 48, a size that is a whole multiple of a drawn size renders that drawing scaled. Leave `font-optical-sizing` at its default (`auto`) so the size picks the drawing. The text family is about 400 KB as woff2 and the display family about 1.7 MB, because every glyph in a file is padded to the rectangle count of its largest grid. `font-weight` 200, 400, and 700 or 800 give Light, Regular, and Bold. Light is a stem count like the others, so it is the same drawing as Regular wherever the two round to the same number of pixels: in the current files at 7 to 16, 23 to 28, 38, and 39px; it is lighter at 17 to 22, 29 to 37, and 40 to 48px.

## Preview

Serve the repo root (`python3 -m http.server`) and open `preview/`: every size from 8 to 48 with the drawing it uses and whether it lands on whole device pixels at your display's density. `build/proof.png` is the same ladder rendered through FreeType and magnified 3×.

## Sources

`glyphs/<grid>/{light,regular,bold}.txt`, one per grid from 7 to 48, are generated from the variable font in `vendor/` and committed so every build is reproducible. Each file names its grid, ascent, descent, cap height, and x-height in a header; each entry is a name, codepoint, an advance in pixels, an optional negative `left` offset (the bitmap starts that many pixels left of the origin, as the tail of `j` does), and a bitmap (`#` ink, `.` clear). `charset.txt` lists the codepoints to render.

## License

The font is licensed under the SIL Open Font License 1.1; its copyright notices are in [vendor/inter/LICENSE.txt](vendor/inter/LICENSE.txt). The scripts and everything else in the repo are MIT ([LICENSE](LICENSE)).
