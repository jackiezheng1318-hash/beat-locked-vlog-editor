#!/usr/bin/env python3
"""Per-shot warm "golden sun" grade that backs off where a fixed warm look turns yellow.

A single warm LUT/filter on every shot over-yellows shots that are already bright or already
warm, and especially faces. So each shot is measured and the warmth is scaled per shot.

For each shot three frames are measured (mean luma, R/B warmth ratio, share of near-white
highlights) and the warm components are scaled by
    k = warmth_factor x brightness_factor   (x 0.45 when the shot features a face)
Bright shots also get a softer highlight roll-off. Everything runs in 16-bit RGB.

CLI (preview / debugging): adaptive_grade.py <video> <start> <duration> [--face]
Library: measure(path, start, dur) -> stats; grade(stats, face) -> ffmpeg filter string
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np


def measure(path, start, dur):
    Ys, RBs, His = [], [], []
    for t in (start + 0.15, start + dur / 2, start + max(dur - 0.15, 0)):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', path, '-frames:v', '1', '-vf', 'scale=160:90',
                              '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
        if len(raw) < 160 * 90 * 3:
            continue
        f = np.frombuffer(raw[:160 * 90 * 3], np.uint8).reshape(90, 160, 3).astype(float)
        Y = f @ [0.299, 0.587, 0.114]
        Ys.append(Y.mean()); RBs.append(f[..., 0].mean() / max(f[..., 2].mean(), 1)); His.append((Y > 215).mean())
    return dict(luma=float(np.mean(Ys)), rb=float(np.mean(RBs)), highlights=float(np.mean(His)))


def grade(st, face=False):
    warm_f = float(np.clip(1 - (st['rb'] - 1.05) * 2.0, 0.35, 1.0))       # already warm -> add less
    bright_f = float(np.clip(1 - (st['luma'] - 115) / 150, 0.55, 1.0))   # bright sun -> add less
    k = warm_f * bright_f * (0.45 if face else 1.0)
    top = 0.95 if (st['highlights'] > 0.08 or st['luma'] > 140) else 0.97
    vib = 0.04 if face else 0.10
    # 16-bit planar RGB end to end. eq is 8-bit only (it collapsed 10-bit sources to ~8-bit), so its
    # contrast 1.03 is folded into the curve and its saturation 1.03 is a Rec.709 channel-mixer matrix.
    c, sat = 1.03, 1.03
    pts = ' '.join(f'{x}/{min(max((y - 0.5) * c + 0.5, 0), 1):.4f}'
                   for x, y in ((0, 0.02), (0.25, 0.23), (0.5, 0.52), (0.75, 0.79), (1, top)))
    lr, lg, lb = 0.2126 * (1 - sat), 0.7152 * (1 - sat), 0.0722 * (1 - sat)
    mix = (f'colorchannelmixer=rr={lr + sat:.5f}:rg={lg:.5f}:rb={lb:.5f}:gr={lr:.5f}:gg={lg + sat:.5f}:gb={lb:.5f}:'
           f'br={lr:.5f}:bg={lg:.5f}:bb={lb + sat:.5f}')
    return (f"format=gbrp16le,colortemperature=temperature=5400:mix={0.45 * k:.3f}:pl=0.5,"
            f"curves=master='{pts}',"
            f"colorbalance=rs=-0.02:bs=0.03:rm={0.012 * k:.4f}:gm=0.005:bm={-0.018 * k:.4f}:"
            f"rh={0.03 * k:.4f}:gh={0.012 * k:.4f}:bh={-0.03 * k:.4f},"
            f"vibrance=intensity={vib}:rbal=0.9:bbal=1.0,{mix}"), k


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    s = measure(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
    g, k = grade(s, '--face' in sys.argv)
    print(s, 'k=%.2f' % k); print(g)
