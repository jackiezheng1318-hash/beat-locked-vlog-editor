#!/usr/bin/env python3
"""Contact sheets of raw footage for shot selection: one thumbnail every --every seconds,
labelled `clip @time` and colour-coded by handheld shake from shot_stability.py
(green steady / yellow some shake / red shaky).

The model (or you) reads these sheets to pick candidate windows for shots.csv.

Usage: raw_contact_sheets.py <out_dir> <stability.json> <clip> [<clip> ...] [--every 2] [--cols 8 --rows 8]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def thumbs(clip, every, tmp):
    stem = os.path.splitext(os.path.basename(clip))[0]; d = os.path.join(tmp, stem); os.makedirs(d, exist_ok=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', clip, '-vf', f'fps=1/{every},scale=256:-2', '-q:v', '5',
                    os.path.join(d, '%05d.jpg')], check=True)
    return stem, sorted(os.path.join(d, f) for f in os.listdir(d))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('stability'); ap.add_argument('clips', nargs='+')
    ap.add_argument('--every', type=float, default=2.0); ap.add_argument('--cols', type=int, default=8)
    ap.add_argument('--rows', type=int, default=8); a = ap.parse_args()
    stab = json.load(open(a.stability)); os.makedirs(a.out, exist_ok=True)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 16)
    except OSError:
        font = ImageFont.load_default()
    items = []
    with tempfile.TemporaryDirectory() as tmp, concurrent.futures.ThreadPoolExecutor(4) as ex:
        for stem, files in ex.map(lambda c: thumbs(c, a.every, tmp), a.clips):
            jit = np.array(stab.get(stem, {}).get('jit', [0])); sf = stab.get(stem, {}).get('fps', 10)
            for i, f in enumerate(files):
                t = i * a.every; seg = jit[int(t * sf):int((t + a.every) * sf)]
                items.append((stem, t, Image.open(f).copy(), float(np.median(seg)) if len(seg) else 0.0))
    TW, TH = 256, 144; per = a.cols * a.rows
    for s in range(0, len(items), per):
        im = Image.new('RGB', (a.cols * TW, a.rows * (TH + 20)), (15, 15, 15)); d = ImageDraw.Draw(im)
        for k, (stem, t, th, j) in enumerate(items[s:s + per]):
            x, y = (k % a.cols) * TW, (k // a.cols) * (TH + 20)
            im.paste(th.resize((TW, TH)), (x, y))
            col = (80, 200, 80) if j < 0.35 else (230, 200, 60) if j < 0.7 else (230, 70, 70)
            d.rectangle([x, y + TH, x + 7, y + TH + 20], fill=col)
            d.text((x + 11, y + TH + 2), f'{stem[-12:]} @{t:.0f}s', fill='white', font=font)
        im.save(os.path.join(a.out, f'sheet-{s // per + 1:02d}.jpg'), quality=82)
    print(len(items), 'thumbnails ->', (len(items) + per - 1) // per, 'sheets in', a.out)


if __name__ == '__main__':
    main()
