# A variable pixel font

_Working design, October 2026. The prototype in this repo builds; the character set, bold tuning, and the opsz grid are open._

## Thesis: a pixel font can be variable only where the variation lands on pixels

A pixel font is a promise that every mark is a whole pixel. Variable fonts are a promise that every design can be interpolated. The two promises conflict unless the thing being varied is itself measured in pixels—and on 2× and 3× displays, in *device* pixels. That is the organizing idea of this font: every axis moves rectangles by pixel-shaped amounts, so the ends of every axis are honest bitmaps and the middle of every axis is crisp on a dense enough screen.

System Six draws its components at one art pixel per whole number of device pixels. This font extends that discipline to type.

## Starting point: the System Six faces

System Six ships Pixel Operator (Jayvee Enaguas, CC0 1.0) in three roles: 16px system and app text, an 8px small face, and a mono. Its metrics are the base of this design and are kept exactly:

| Metric | Pixels |
|---|---|
| Em | 16 (100 font units per pixel on a 1600-unit em) |
| Ascent / descent | 13 / 3 (baseline sits 3 rows up; line height 16 with no gap) |
| Cap height, ascender | 9 |
| x-height | 7 |
| Stem | 1 (Regular), 2 (Bold) |
| Typical advance | 7 for a 5-wide letter with one pixel of bearing each side; Bold adds 1 |

Pixel Operator Bold is the Regular smeared one pixel to the right with the advance grown by one—the same rule the 1980s system used to synthesize bold. That rule is what makes a weight axis possible.

## The model: ink is rectangles, and rectangles interpolate

Every glyph is a text bitmap. The build turns ink into rectangles and emits one TrueType contour per rectangle, overlapping where they touch. Because every master has the same rectangles in the same order, any transform that only moves or resizes rectangles is a valid variable-font master.

Three transforms fall out of that, and each one is a classic bitmap operation made continuous:

| Axis | Transform | Ends | Why it stays crisp |
|---|---|---|---|
| **Weight** `wght` 400–700 | Every rectangle grows to the right by _k_ pixels; the advance grows by _k_ | 1px and 2px stems, matching Pixel Operator Regular and Bold | At 550 the stem is 1.5px: blurry at 1×, exactly 3 device pixels at 2× |
| **Slant** `slnt` 0 to −18° | Each row shifts right by ⌊y / 3⌋ pixels, baseline fixed | Upright, and a true shear | Whole-pixel shifts at the end; half-pixel shifts at 2× in the middle |
| **Roundness** `ROND` 0–100 | Every pixel's corner radius grows from 0 to half a pixel | Squares, and dots | Decorative; crisp only at 0 |

The axes are independent, so the build uses one sparse master per axis end rather than every corner of the cube. Bold + slanted + round is the sum of three deltas and needs no master of its own.

**Primitive choice.** With `--primitive pixels` every source pixel is a 12-point rounded rectangle, which is what makes `ROND` possible. With `--primitive runs` every horizontal run is a 4-point rectangle. At 241 glyphs the woff2 sizes are 8 KB and 6 KB, so the pixel primitive is the default; the run primitive exists for a minimal install build.

**What this model cannot do.** It cannot interpolate between two different drawings. A hand-drawn Bold whose runs are not supersets of the Regular's runs has no correspondence, and a condensed width is a different drawing entirely. The containment rule in the next section is the escape hatch for Bold; a width axis is out of scope.

## Weight: smear by default, hand-tune by exception

Smearing works for most of Latin, and it is exactly what the original Bold did. It fails in two places: tight counters that close (`a`, `e`, `s` at 2px stems in a 5-wide letter) and glyphs whose rhythm depends on the right stem staying put.

The plan is to accept a per-glyph `bold:` bitmap in the source that overrides the smear. The build maps it onto the Regular with a **containment rule**: each Bold row must have no more runs than the Regular row, and every Regular run must sit inside a Bold run. Regular runs that share a Bold run are extended rightward until they meet. Anything that fails the rule is a build error with both bitmaps printed, so a stray pixel is caught at build time rather than in a menu.

A Black master (3px stems) is possible under the same rule but needs every glyph redrawn wider, so it is not in the first release. The axis is 400–700 until there are drawings that earn 900.

## Scaling to any size is a rule, not a feature

No pixel font scales continuously. The rule for crisp text is:

> **font-size × devicePixelRatio must be a whole multiple of 16.**

| Display | Crisp CSS sizes for the 16 grid |
|---|---|
| 1× | 16, 32, 48, 64 |
| 2× | 8, 16, 24, 32, 40, 48 |
| 3× | 16 / 3 steps: 5.33, 10.67, 16, 21.33, 26.67, 32 |

Everything else antialiases symmetrically, which is tolerable but not the point. Three things make this good rather than merely true:

1. **The specimen states it.** The preview page shows whether the current size is crisp at the viewer's density. Any consumer stylesheet can compute the same thing, and System Six already does for its own `--s6-px`.
2. **An 8-grid companion face** covers the small end and gives 1× displays crisp 8, 24, and 40. It is a separate drawing (Pixel Operator 8 is the model), built from the same source format with `ASC`/`DESC` of 7/1.
3. **A grid axis is possible but experimental.** Variable fonts cannot hold two incompatible drawings, but they can hold two drawings padded to the same rectangle count, with an `avar` map so steep that the interpolation band is invisible: user `opsz` 8–11 on the 8 grid, 12 and up on the 16 grid. With `font-optical-sizing: auto`, small text would switch grids by itself. This is a real technique and a real hack; it is phase 4, after the drawings exist, and only if the padding cost is small.

Rendering notes that matter: set `-webkit-font-smoothing: none` only on 1× screens (it disables subpixel AA, which hides the half-weights on 2×); include a `gasp` table so Windows renders the design size without grayscale; never rely on `image-rendering`, which does not apply to text.

## Character set: System Six first, then scripts

The order is driven by what System Six and its apps render, not by glyph count:

1. **Latin core** (the 238 Pixel Operator codepoints, imported) plus the UI set: ⌘ ⌥ ⇧ ⌃ ⎋ ⌫ ⏎ ✓ ✗ • … – — ‹ › « » ‘ ’ “ ” and the arrows.
2. **Latin extended** to the Google Fonts Latin Plus set (~600 glyphs): all of Western, Central, and Northern European languages, Vietnamese excluded until marks stack.
3. **Marks and composition.** Draw the ~30 combining marks once and give bases `top`/`bottom` anchors in pixel coordinates; the build composes accented glyphs from anchors and emits `mark`/`mkmk`, so uncommon combinations render too.
4. **Greek and Cyrillic.** Both fit the 9/7/3 metrics; both are what separates a UI font from a game font.
5. **Symbols that are native to a pixel grid**: box drawing, block elements, geometric shapes, Braille, and the legacy computing block. These are the one place a pixel font is strictly better than a vector one.

Emoji and CJK are out of scope.

## OpenType features are where "modern" lives

| Feature | Behaviour |
|---|---|
| `kern` | Pair and class kerning in whole pixels (`To`, `AV`, `r.`). Pixel Operator has none; one pixel of kerning at 16px is visible. |
| `tnum` / `pnum` | Digits are tabular by default (7 wide); proportional `1` is an alternate. |
| `zero`, `ss01`… | Slashed and dotted zero; single-storey `a` and `g`; serifed `I` and `l`; a round `0`. |
| `case` | Punctuation and brackets raised one pixel for all-caps text. |
| `frac`, `sups`, `subs`, `numr`, `dnom` | Drawn 5px figures, not scaled. |
| `smcp` | Small caps at x-height (7) with 1px stems. |
| `calt` | Code ligatures in the mono (`->`, `=>`, `!=`, `<=`) as alternates, off by default. |
| `locl` | Turkish `i`, Romanian comma-below, Dutch `ĳ`. |
| `mark`, `mkmk`, `ccmp` | From the anchors above. |

Features are written in plain `.fea` and compiled by `fontTools.feaLib` at build time. Classes come from the glyph names, so kerning is written once for `A` and applies to `Á`.

## Source format: text bitmaps, one file per block

The source is text, like System Six's art. One file per Unicode block in `glyphs/`, entries separated by blank lines:

```
name: a
unicode: U+0061
advance: 7

........
..###...
.#...#..
.....#..
..####..
.#...#..
.#...#..
..####..
```

Planned keys, all optional: `bold:` (the override bitmap), `anchors: top=3,9 bottom=3,0`, `compose: e + acute@top`, `alt-of: a` for stylistic sets, `kern-class: O`. The parser is forty lines and the format diffs like code, which is the point: the font is reviewed in pull requests.

## Build: fontTools, no font editor

`scripts/build.py` parses the sources, writes one static TTF per master, assembles a designspace in memory, and calls `varLib.build`. It sets the overlap flag on every compound glyph, writes a proper name table and `STAT`, and saves TTF and woff2. It runs in a second. The import script that produced `glyphs/latin.txt` from Pixel Operator stays in the repo so the provenance is reproducible.

Not using a font editor is deliberate: the shapes are bitmaps, every transform is arithmetic, and every output is derived. Glyphs or FontForge would add a binary source file to a project whose whole advantage is that it has none.

## Prior art, and what is new here

Variable pixel fonts exist, and the closest ones share a trait: they vary the *element* rather than the *drawing*.

- **Handjet** (Rosetta, OFL) is the most complete: 23 element shapes, weight as element size, and Latin, Greek, Cyrillic, Arabic, Hebrew, Armenian, and Korean. It is a modular display face; weight shrinks the dots rather than thickening stems, so it is not crisp at UI sizes except at one end.
- **Doto** (Óliver Lalan, OFL, 2024) has `wght` as dot size and a `ROND` 0–100 axis—the same tag and range this design uses for roundness. Latin only, on a 6×10 matrix.
- **Pixelify Sans** (Stefie Justprince, OFL) is a pixel face with a 400–700 weight axis.
- **Sixtyfour** and **Workbench** (OFL) are Commodore and Amiga pixel fonts with `BLED` (horizontal pixel bleed) and `SCAN` (scanline height) axes and a small glyph set.
- Pixel Operator, Silkscreen, Departure Mono, and the Jersey family are static.

What none of them do, as far as I could find, is build the weight axis from the system smear so that 400 and 700 are the historical Regular and Bold and 550 is a legitimate 2× weight, add a pixel-row slant, keep the 16-grid metrics that a UI kit draws against, and carry a UI-grade character set with kerning and features. That combination is the product. `ROND` is a nice extra that Doto already proved; it is not the reason to build this.

## Sequencing

1. **Now (done in this repo):** import, build, specimen; `wght`, `slnt`, `ROND` working on 241 glyphs.
2. **Make it a font:** `bold:` overrides with the containment rule; kerning and `tnum`/`zero`/`case`; the UI symbols; a name; an OFL or MIT decision; System Six switches to it behind `--s6-font-system`.
3. **Make it broad:** anchors and composition, Latin Plus, Greek, Cyrillic, box drawing; the 8-grid face; the mono as a second family from the same sources.
4. **Experiments:** the `opsz` grid switch; a Black master; a bleed axis for CRT rendering if System Six ever wants it.

## Open decisions

- **Name.** The build takes `--family`; nothing is committed to.
- **License.** MIT matches the org default; OFL is what every peer font uses and what Google Fonts requires.
- **Slant angle.** 18° (one pixel every three rows) reads as a shear at 16px; 14° (one in four) may suit text better. Both are one constant.
- **Whether `ROND` ships in the main file** or as a separate dots build. It costs 2 KB and nothing else.
