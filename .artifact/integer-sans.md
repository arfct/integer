---
title: Integer Sans
date: 2026-10
category: system
tags:
  - web
  - design
url: https://arfct.github.io/integer/
links:
  source: https://github.com/arfct/integer
media:
  - src: specimen.png
    caption: The specimen on a display of one device pixel per pixel, a line of Regular at each size from 7 to 39
    alt: A white web page with rows of the sample text Hamburgefonstiv 0123456789 growing from very small to large, each row labelled at the left with its size in pixels and the drawing it uses
unconfirmed:
  - date
---

A weight in Integer Sans is a whole number of pixels of stem, so at 16 pixels and below Light and Regular both come to one pixel, and 17 is the first size at which the three weights measure one, two and three. Every pixel size from 7 to 48 has its own bitmap drawing in each weight. A browser picks one from the font size and does not interpolate between two. The model is the font suitcase of the 1980s, which held hand-drawn bitmaps at six sizes and left the system to pick the one that matched. Here the container is a variable font whose size and weight axes move in steps, issued as two families, Integer Sans for sizes 7 to 24 and Integer Sans Display for 25 to 48.

A script renders the drawings from Inter, the source typeface, onto each grid, and mirrors the letters that the source draws symmetric so that both sides of an A or an O take the same staircase. Hand corrections are kept in separate override files. After each build a check renders every size through FreeType and fails on any grey pixel.

Integer Sans is a prototype. Its character set is Latin-1, it has no kerning, and sizes below 9 are present but not readable.

Python, fontTools, FreeType. 2026.
