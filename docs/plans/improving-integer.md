# Improving Integer Sans: next steps

_Plan, 2026-10-23. Follows a short research pass on current rasterization and pixel-art practice; see References._

## Thesis: large sizes are solved, small sizes are a search problem, and search is now cheap

Rasterizing an outline at 25px and up is a solved problem: antialiasing does the work, hinting is ignored by macOS and mostly by Windows, and Integer Sans Display proves the pipeline needs no help there beyond the pixel-perfect thinning. Below about 20px every pixel is a decision, and the historical answer is the hand: TrueType bytecode written stem by stem, or bitmap fonts drawn one glyph at a time. The pipeline already automates the first draft of that work with rows fixed per grid, stems chosen on the source's weight axis, coverage-guided thinning, and mirroring.

What is different now is not a better rasterizer. It is that **evaluating a candidate bitmap is cheap and objective enough to run millions of times**, so the small sizes can be treated as a search: render several plausible bitmaps per glyph and size, score each against the outline and against structural rules, keep the best, and spend human attention only on the residue the scores cannot settle. The hand stays in the loop through the override files; the loop just gets shorter.

## What the field does, and what to take from it

- **Hinting** (TrueType instructions, ttfautohint, FreeType's autohinter) snaps stems and blue zones per size. It is exactly the vertical and horizontal discipline the importer already applies, and the Glyphs documentation's own rule of thumb, that hinting pays off between 12 and 40 ppem, matches where Integer's text face lives. Take: keep the autohinter as the stem snapper; do not write bytecode.
- **Pixel-font craft** is consistent: one stroke weight across the alphabet, shared cap height and x-height, deliberate differences between confusable pairs (`I l 1`, `O 0`), generous spacing, and redrawing rather than shrinking. Take: these are checkable rules, and the check script should enforce them, not only the proof sheet.
- **Vector-to-pixel optimisation**: Kopf et al. (2013) pose downscaling as fitting per-pixel kernels and note it keeps linear features of vector input sharp and connected; Öztireli and Gross optimise the downscaled image directly against SSIM; Gerstner et al. (2012) pixelate by joint segmentation and palette. Take: a fidelity score between a candidate bitmap and the antialiased outline (SSIM at 2× to 4×) is a sound objective, and the thinning rules act as the structural prior these methods lack for type.
- **Learned pixelisation** (Wu et al., SIGGRAPH Asia 2022, cell-controllable and aliasing-aware; SD-πXL, 2024) generates pixel art from images. Take: not for drawing glyphs, where fidelity to the source outline is the point and the rule-based pipeline is already exact, but worth a benchmark on the hardest glyphs at 9 to 12px to see whether a learned prior beats the rules there.
- **Legibility measurement**: OCR confidence is the only automated proxy with any track record, weakly correlated with design features and sensitive to size; nothing validated exists for CLIP-style scoring. Take: use OCR as a regression alarm over pangrams per size, never as the objective.

## What is uniquely possible now

1. **Exhaustive candidate search.** The importer renders all 42 grids in eight minutes in pure Python. With the pixel loops vectorised, rendering eight candidates per glyph (sub-pixel x offsets of 0, ¼, ½, ¾; hinter on and off; two x-height roundings) for 237 glyphs at 42 sizes and three weights is minutes, and scoring them is seconds.
2. **Objective scoring at scale.** Fidelity (SSIM against the antialiased outline), structure (stroke-width histogram against the target, no doubles, mirror symmetry where expected, crossbars present, connected-component count equal to the outline's), and consistency across the alphabet (one x-height rounding per size, chosen by the aggregate score, never per glyph).
3. **Vision models as reviewers, not drawers.** A contact sheet of every glyph at a size, with the outline beside it, can be read by a vision model to flag the ones that look wrong, in minutes, every build. It is a triage tool that points the human at the hundred glyphs that need a hand, out of thirty thousand.
4. **A review loop that lands in text.** Every drawing is already a text file with an override file beside it, so a web page listing the worst-scoring glyphs with a pixel editor that writes the override is a small build on what exists, and every correction is a diff in a pull request.

## Plan

### 1. Measure (first)

Add `scripts/score.py`: for every glyph, size, and weight it renders the outline antialiased at 4× and reports fidelity (SSIM of the bitmap upsampled 4× against it), the stroke-width histogram against the stem and bar targets, doubles, symmetry where listed, crossbars, and the connected-component count against the outline's. It writes `build/scores.json`, a contact sheet of the worst hundred, and a per-size OCR confidence over a pangram. The check script fails on structural regressions; fidelity is reported, not gated, until there is a baseline.

Done when: a scoreboard exists for the current drawings, committed with the build, and the worst hundred are a list rather than a feeling.

### 2. Search instead of a single render

Make the importer generate candidates and let the scorer choose, under two constraints: metric rows are chosen once per size by the aggregate score over the whole alphabet, and structural rules are hard constraints, not terms in the score. Fix the known defect that the thinning erodes diagonal arms beside a crossing (`X`, `x`, `k`) by treating a crossing as a junction whose arms keep full width.

Done when: the scoreboard improves at every size without a single hand override, and `X` and `x` keep their arm width at the 2px weights.

### 3. Hand correction with tooling

Publish a review page on the Pages site: every glyph at a chosen size and weight with its outline beside it, sorted by score, with a pixel editor that writes `glyphs/<grid>/<weight>.overrides.txt`. Run a vision-model triage over the contact sheets on each build and post its flags as a list in the build output. Work the list from 9 to 16px first, where the text face is used most.

Done when: the worst hundred at 9 to 16px have been looked at by a person, and the override files carry the decisions.

### 4. Spacing and kerning

Round the source's sidebearings consistently per size rather than per glyph, keep symmetric glyphs centred, and derive class kerning from the source's pair positioning rounded to whole pixels with a minimum of one, compiled as a `kern` feature with feaLib. Make figures tabular by default. This is the largest single improvement to how text reads that the drawings themselves cannot give.

Done when: `To`, `AV`, `r.`, and `11` kern at 12 and 16px and a pangram's rhythm matches the source's at 2×.

### 5. Character set

Extend `charset.txt` to Latin Plus, then Greek and Cyrillic; the pipeline renders whatever the source has, and only the symmetry lists need extending per script. Draw by hand what the source lacks and System Six needs: ⌘ ⌥ ⇧ ⌃ ⎋ ⌫ ⏎ ✓ ✗, box drawing, and block elements, which are the one place a pixel font is strictly better than a vector one.

Done when: System Six renders every string it has in Integer Sans without a fallback glyph.

### 6. Make it transferable

Move the face-specific parts of the importer into a config next to the vendored font: axis tags, reference glyphs for the metric lines and the stem and bar probes, the symmetry lists, and the charset. Prove it by running a second sans through the pipeline unchanged.

Done when: a second face builds from a config and the scoreboard, with no edits to the importer.

### 7. Packaging decisions

Decide what Light means below 23px, where it equals Regular today, or drop it there. Decide whether the display family's 1.7 MB is acceptable or whether it splits again at 32. Add an `EBDT` bitmap export for Linux and embedded use, which FreeType honours and which costs nothing because the bitmaps already exist. Settle whether `opsz` should follow CSS pixels or device pixels for System Six on 1.5× displays.

## Not on the plan

- Generative models drawing glyphs. Fidelity to the source outline is the product; a model can review, not draw.
- Hand-written TrueType hinting. The bitmaps are the hinting.
- Sizes below 8. The 7px grid exists and is exact; a 5-pixel cap is not a reading size, and no amount of search changes that.

## References

- Kopf, Shamir, Peers. *Content-Adaptive Image Downscaling.* SIGGRAPH Asia 2013. https://www.cs.wm.edu/~ppeers/publications/Kopf2013CID/Kopf_SIGGRAPHAsia2013.pdf
- Gerstner et al. *Pixelated Image Abstraction.* NPAR 2012; extended in Computers & Graphics 2013.
- Öztireli, Gross. *Perceptually Based Downscaling of Images.* SIGGRAPH 2015 (SSIM as the objective).
- Wu et al. *Make Your Own Sprites: Aliasing-Aware and Cell-Controllable Pixelization.* SIGGRAPH Asia 2022. https://dl.acm.org/doi/10.1145/3550454.3555482 — code: https://github.com/WuZongWei6/Pixelization
- *SD-πXL: Generating Low-Resolution Quantized Imagery via Score Distillation.* 2024. https://arxiv.org/abs/2410.06236
- Glyphs, *TrueType autohinting* (the 12 to 40 ppem rule of thumb). https://glyphsapp.com/learn/hinting-truetype-autohinting
- Microsoft Typography, *TrueType hinting.* https://learn.microsoft.com/en-us/typography/truetype/hinting
- *Pixel Fonts and Bitmap Type: Drawing Readable Letters in a Tiny Grid.* https://the-pixel.art/articles/pixel-fonts-bitmap-fonts/
- *The Effect of Fonts Design Features on OCR for Latin and Arabic* (OCR as a weak legibility proxy). https://www.researchgate.net/publication/287401836
