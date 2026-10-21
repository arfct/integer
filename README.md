# Integer

Integer is a variable pixel font built from text bitmaps, where every rendered instance is a real drawing and every value is a whole number. The size axis is stepped: it holds a drawing per pixel grid (8 and 16 rows today) and the browser picks one from the font-size, never an interpolation. The weight axis steps the same way between 1px and 2px stems. The grids and metrics are those of the System Six faces, so it drops in where Pixel Operator is used today.

The design, its reasoning, and the roadmap are in [docs/design.md](docs/design.md).

## Stepped build (the direction)

```bash
uv venv && uv pip install 'fonttools[woff]'
cd experiments/stepped && ../../.venv/bin/python build.py out
```

Writes `experiments/stepped/out/IntegerStep-VF.woff2`; `test.html` next to it shows every size and weight step and measures gray pixels on a canvas. Add `-webkit-font-smoothing: none` on macOS to see true bitmaps.

## Continuous build (the first prototype)

```bash
uv venv && uv pip install 'fonttools[woff]'
.venv/bin/python scripts/build.py
```

Writes `build/Integer-VF.ttf` and `.woff2`. `--family NAME` sets the family name; `--primitive runs` builds the smaller, square-only variant without the roundness axis.

## Preview

Serve the repo root (`python3 -m http.server`) and open `preview/`. The sliders drive the three axes, and the page says whether the current size is crisp at your display's density: font-size × devicePixelRatio must be a multiple of 16.

## Sources

`glyphs/*.txt` are the font. Each entry is a name, codepoints, an advance in pixels, and a bitmap (`#` ink, `.` clear) with 13 rows above the baseline and 3 below. `glyphs/latin.txt` was imported from Pixel Operator (Jayvee Enaguas, CC0 1.0) with `scripts/import-pixel-operator.py`.
