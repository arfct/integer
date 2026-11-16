"""Fetch the hand-drawn reference strikes the audit compares against.

    .venv/bin/python experiments/hand-drawn/fetch_refs.py

Downloads twelve BDF files (a grotesque sans hand-tuned for the screen at 8,
10, 12, 14, 18 and 24 px, regular and bold) from the X.Org 75dpi font package
into experiments/hand-drawn/out/ref, which git ignores. They are read for
measurement only and are not part of the font; their licence is in each
file's header.
"""
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out', 'ref')
BASE = 'https://gitlab.freedesktop.org/xorg/font/adobe-75dpi/-/raw/master/'

os.makedirs(OUT, exist_ok=True)
for weight in 'RB':
    for size in ('08', '10', '12', '14', '18', '24'):
        name = f'helv{weight}{size}.bdf'
        path = os.path.join(OUT, name)
        if not os.path.exists(path):
            urllib.request.urlretrieve(BASE + name, path)
        print(path, os.path.getsize(path))
