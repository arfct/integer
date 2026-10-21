# Integer: a variable pixel font

_Working design, October 2026. The font is named Integer. `scripts/build.py` builds the stepped model across seven grids and every exact size to 48, and `scripts/check.py` proves each instance is a bitmap through FreeType. The continuous prototype lives in `experiments/continuous/`. The character set, bold tuning, and hand correction of the derived grids are open._

## Thesis: a pixel font is a bundle of drawings, and a variable font is the modern bundle

A pixel font is a promise that every mark is a whole pixel. That promise cannot survive scaling: a 16-row drawing is a bitmap at 16 pixels and a blur at 15. The 1980s answer was a suitcase of hand-drawn sizes, 9, 10, 12, 14, 18, and 24 point, and the system picked the one that matched. That answer is still right. What changed is the container: a variable font with a **stepped size axis** holds every drawing, the browser picks one from the font-size by itself, and nothing in between ever renders.

The same trick makes weight honest. A stepped weight axis holds a 1px drawing and a 2px drawing and snaps between them, so `font-weight: 550` renders the one or the other, never an overlap of both. Every rendered instance is a drawing someone made.

System Six draws its components at one art pixel per whole number of device pixels. This font extends that discipline to type, with the same rule in the other direction: the font-size, times the display density, picks a drawing that exists.

## Starting point: the System Six faces

System Six ships Pixel Operator (Jayvee Enaguas, CC0 1.0) in three roles: 16px system and app text, an 8px small face, and a mono. Its two grids are the first two drawings of this font and their metrics are kept exactly:

| Metric | 16-row grid | 8-row grid |
|---|---|---|
| Units per pixel on the 1600 em | 100 | 200 |
| Ascent / descent in rows | 13 / 3 | 7 / 1 |
| Cap height, ascender | 9 | 7 |
| x-height | 7 | 5 |
| Stems: Regular, Bold | 1, 2 | 1, 2 |
| Advance of a 5-wide letter | 7 (Bold 8) | 7 (Bold 8) |

Both Bolds are the Regular smeared one pixel to the right with the advance grown by one, the rule the original system used to synthesize bold. That rule is why a smeared Bold needs no drawing of its own, and it is also the limit of what can be derived: a Light cannot be derived, because nothing is thinner than one pixel.

## The model: ink is rectangles, axes are stepped, and every instance is a bitmap

Every glyph is a text bitmap. The build turns ink into rectangles and emits one TrueType contour per rectangle. Drawings on different grids have different rectangle counts, so the build pads every glyph to the largest count with zero-size rectangles; that makes any two drawings "compatible" in the variable-font sense, even though interpolating between them would be nonsense.

The nonsense is never shown. Each axis carries an `avar` map so steep that the interpolation band is a thousandth of the axis wide:

| Axis | User range | Renders | Switch |
|---|---|---|---|
| **Size** `opsz` | 8–16 | the 8-row drawing below 12, the 16-row drawing from 12 | 11.99 → 12 |
| **Weight** `wght` | 400–700 | 1px stems below 550, 2px stems from 550 | 549.99 → 550 |

Browsers set `opsz` from the font-size when `font-optical-sizing: auto` is on (the default), so a consumer writes `font-size: 10px` and gets the 8-row drawing at 1.25× scale, or `font-size: 8px` and gets it exactly. Sizes above the largest grid clamp to it, so 32px is the 16-row drawing at 2×, which is also crisp.

**Verified in Chrome on a 2× display**, by measuring advance widths in the DOM at every size from 8 to 24: each size picks exactly one drawing, 11.5px included, and the 550 weight boundary snaps. Rendering the same text to a canvas with `-webkit-font-smoothing: none` gives **zero gray pixels** at 16px; without it, macOS text smoothing adds a one-device-pixel fringe at about 20% gray around every edge. That fringe is the renderer, not the font, and the CSS turns it off for DOM text. (Chrome's canvas picked the 8-row drawing at exactly 16px, which I could not explain; DOM text was right at every size.)

**What this model gives up.** Continuous axes. The first prototype has a continuous weight (a 1.5px stem is exactly 3 device pixels at 2×), a slant that shears rows, and a roundness axis that turns pixels into dots. Those are real and cheap, and the roundness one is the trick the existing variable pixel fonts rely on, but they are decorative next to the promise above. They can ship as a separate file. The main font steps.

## Weights are quantized by the grid, and names follow a ratio

A weight is a stem count, and a stem count only means something relative to the letter. Define weight by stem-to-cap-height ratio and round to whole pixels with a floor of one:

| Weight | Stem / cap | 16-row (cap 9) | 32-row (cap 18) | 48-row (cap 27) |
|---|---|---|---|---|
| 200 Light | ~5% | 1 (same as Regular) | 1 | 1 |
| 400 Regular | ~11% | 1 | 2 | 3 |
| 800 Bold | ~22% | 2 | 4 | 6 |

Two consequences. **Light does not exist at small grids**: the 16-row 200 is the 400, exactly as the old suitcases had no Light at 9 point. The font says so by giving the 200 master the Regular's drawing, so the step is a no-op rather than an error. **Light appears on dense displays by itself**: 16px text at 2× is 32 device pixels, so if the font has a 32-row drawing, `opsz` 16 on a 2× screen could pick it and render a true 1-device-pixel Light. Whether `opsz` should mean CSS pixels (the CSS rule) or device pixels (what crispness wants) is a consumer decision; System Six already computes its density and can set `font-variation-settings: "opsz" N` explicitly.

Smearing covers 400 → 800 on every grid and matches the historical Bolds. Where it closes a counter (`a`, `e`, `s` at 2px stems in a 5-wide letter), a per-glyph `bold:` bitmap in the source overrides it. Because the axis is stepped, the override has no compatibility constraint beyond rectangle count, which the padding handles. The first prototype's "containment rule" is no longer needed.

## The grid list is the real design work

The suitcase had six sizes. Every grid is a drawing of the whole character set, so the list has to be small and earn each entry. The candidate rule: cover every CSS size from 8 to 16 at 1×, 2×, and 3×, then rely on integer scaling above that.

| Grid (rows) | Serves at 1× | at 2× | at 3× |
|---|---|---|---|
| 8 | 8, 16, 24 | 4, 8, 12 | 5.33, 8 |
| 10 | 10, 20, 30 | 5, 10, 15 | 10 |
| 12 | 12, 24, 36 | 6, 12, 18 | 8, 12 |
| 14 | 14, 28 | 7, 14, 21 | 14 |
| 16 | 16, 32, 48 | 8, 16, 24 | 16, 32 |
| 20 | 20, 40 | 10, 20, 30 | 20 |
| 24 | 24, 48 | 12, 24, 36 | 24 |

Eight to sixteen rows is where every pixel is a decision and the drawings must be by hand. Above that, a drawing can start as the 16-row one scaled by an integer, or as a rasterization of a vector skeleton, and be corrected where it reads badly. METAFONT solved exactly this in 1984, parameters in and pixel-exact bitmaps out at any resolution, and a stroke skeleton with a pixel-art rasterizer is the pragmatic version of it: it drafts the 20-, 24-, and 32-row grids, and the designer fixes the glyphs that matter.

**Recommendation:** ship 8 and 16 first (they exist), add 12 (the most-used UI size on 1× Windows and the 2× size of 6, which nobody uses, so really a 1× grid), then 10 and 24. Decide 14 and 20 from use.

## Delivery: one variable file, and the platform question

**On the web**, one woff2 with stepped `opsz` and `wght` is the whole deliverable. It works wherever variable fonts do, and `font-optical-sizing: auto` makes size selection automatic. Consumers add `-webkit-font-smoothing: none` on macOS and never need to know how many drawings are inside. At 241 glyphs and two grids the file is 14 KB; the cost grows with the largest grid's rectangle count, not with the number of grids, because of the padding, so a 24-row grid roughly triples it. Fine.

**Embedded bitmap strikes** (`EBDT`/`EBLC`, the TrueType form of the suitcase) still exist in the OpenType spec and FreeType still honours them, so Linux and Android would use real bitmaps. macOS CoreText does not render monochrome strikes, and DirectWrite uses them only in its GDI-compatible modes, so browsers on the two desktop platforms that matter would ignore them. They are a legitimate addition for native Linux and embedded use and the build could emit them from the same bitmaps; they are not the primary mechanism.

**Hinting** is the other historical route to pixel-exact rendering at every size, and it is dead on the web: CoreText and Chrome on macOS ignore TrueType instructions, and DirectWrite runs them only partially. Not pursued.

**Native apps** get the same variable file. The one platform-specific note is that macOS stem darkening is on for all text, so a native app wants the aliased rendering mode (`NSFontSmoothing` off, or Core Text's antialiasing disabled) to see bitmaps.

## Character set: System Six first, then scripts

The order is driven by what System Six and its apps render, not by glyph count, and every grid must carry the whole set, which is the strongest argument for a short grid list:

1. **Latin core** (the 238 Pixel Operator codepoints, imported) plus the UI set: ⌘ ⌥ ⇧ ⌃ ⎋ ⌫ ⏎ ✓ ✗ • … – — ‹ › « » ‘ ’ “ ” and the arrows.
2. **Latin extended** to the Google Fonts Latin Plus set (~600 glyphs), Vietnamese excluded until marks stack.
3. **Marks and composition.** Draw the ~30 combining marks once per grid and give bases `top`/`bottom` anchors in pixel coordinates; the build composes accented glyphs and emits `mark`/`mkmk`.
4. **Greek and Cyrillic.**
5. **Symbols native to a pixel grid**: box drawing, block elements, geometric shapes, Braille, and the legacy computing block.

Emoji and CJK are out of scope.

## OpenType features are where "modern" lives

| Feature | Behaviour |
|---|---|
| `kern` | Pair and class kerning in whole pixels, per grid. One pixel at 16px is visible. |
| `tnum` / `pnum` | Digits tabular by default; proportional `1` as an alternate. |
| `zero`, `ss01`… | Slashed and dotted zero; single-storey `a` and `g`; serifed `I` and `l`. |
| `case` | Punctuation raised one pixel for all-caps text. |
| `frac`, `sups`, `subs` | Drawn small figures, not scaled. |
| `smcp` | Small caps at x-height. |
| `calt` | Code ligatures in the mono, off by default. |
| `locl` | Turkish `i`, Romanian comma-below, Dutch `ĳ`. |

Features are plain `.fea`, compiled by `fontTools.feaLib` at build time. Kerning values vary by grid through the same `opsz` masters.

## Source format: text bitmaps, one file per block per grid

One directory per grid (`glyphs/16/`, `glyphs/8/`), one file per Unicode block, entries separated by blank lines:

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

Planned keys, all optional: `bold:` (override bitmap), `anchors:`, `compose: e + acute@top`, `alt-of:`, `kern-class:`. A glyph missing from a grid falls back to the nearest grid scaled by an integer, so a new grid can start sparse. The format diffs like code; the font is reviewed in pull requests.

## Build: fontTools, no font editor

The build parses every grid, pads rectangle counts, writes one static TTF per (grid, weight) master, assembles a designspace with stepped `avar` maps, and calls `varLib.build`. It sets the overlap flag, writes `name` and `STAT`, and saves TTF and woff2. `experiments/stepped/build.py` is the working proof at two grids and two weights; `scripts/build.py` is the earlier continuous build and becomes the optional decorative file.

## Prior art

- **Handjet** (Rosetta, OFL) is the broadest variable pixel font: 23 element shapes, weight as element size, seven scripts. Weight shrinks dots rather than thickening stems, and nothing snaps to a grid.
- **Doto** (Óliver Lalan, OFL, 2024): dot-size weight and a `ROND` roundness axis, Latin only.
- **Pixelify Sans** (OFL): a 400–700 weight axis on a pixel face, continuous.
- **Sixtyfour** and **Workbench** (OFL): C64 and Amiga drawings with CRT bleed and scanline axes.
- Pixel Operator, Silkscreen, Departure Mono, and the Jersey family are static, one grid each.

All of the variable ones interpolate pixel shapes, which is the overlap effect. None uses the axes as a selector for discrete drawings, and none ships more than one grid. The stepped model is the new part; the drawings are the work.

## Sequencing

1. **Done:** grids 8, 9, 10, 11, 12, 14, 16 (the odd ones derived, not yet hand-corrected) and their multiples to 48, Regular and Bold, in one 65 KB file; every exact size verified bitmap-exact through FreeType, and the drawing selection verified in Chrome's DOM. The gvar tents are neighbour-bounded so no fixed-point drift reaches a master.
2. **Make it the font:** hand-correct the derived grids where the rules fell short (accents on capitals at 12, descenders at 9); `bold:` overrides; kerning, `tnum`, `zero`, `case`; the UI symbols; a license; System Six switches to it.
3. **Make it broad:** the 12-row grid; anchors and composition; Latin Plus, Greek, Cyrillic, box drawing; the mono.
4. **Later:** 10- and 24-row grids from a skeleton rasterizer; `EBDT` strikes for Linux; the continuous decorative file.

## Open decisions

- **License** (MIT per the org default, or OFL like every peer font). The name is Integer: every value in the font is a whole number.
- **Does `opsz` mean CSS pixels or device pixels** for the consumers we control. CSS pixels is the standard; device pixels is what crispness wants on 1.5× displays.
- **Which grids** beyond 8, 12, and 16.
