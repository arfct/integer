# Pixel Variable

A variable pixel font built from text bitmaps. Weight, slant, and roundness are real axes: the bold is the classic one-pixel smear made continuous, the slant shifts pixel rows, and roundness turns squares into dots. The grid and metrics are those of the System Six faces (16 rows per em, 13 above the baseline), so it drops in where Pixel Operator is used today.

The design, its reasoning, and the roadmap are in [docs/design.md](docs/design.md).

## Build

```bash
uv venv && uv pip install 'fonttools[woff]'
.venv/bin/python scripts/build.py
```

Writes `build/PixelVariable-VF.ttf` and `.woff2`. `--family NAME` sets the family name; `--primitive runs` builds the smaller, square-only variant without the roundness axis.

## Preview

Serve the repo root (`python3 -m http.server`) and open `preview/`. The sliders drive the three axes, and the page says whether the current size is crisp at your display's density: font-size × devicePixelRatio must be a multiple of 16.

## Sources

`glyphs/*.txt` are the font. Each entry is a name, codepoints, an advance in pixels, and a bitmap (`#` ink, `.` clear) with 13 rows above the baseline and 3 below. `glyphs/latin.txt` was imported from Pixel Operator (Jayvee Enaguas, CC0 1.0) with `scripts/import-pixel-operator.py`.
