#!/usr/bin/env python3
"""Per-0.1 s handheld stability for raw clips, used to pick in-points that don't shake.

Decodes each clip to 192x108 gray @10 fps (VideoToolbox when available), then per frame:
  jit   = deviation of the phase-correlation shift from its 1 s moving average (shake)
  pan   = 1 s average shift (intentional camera move)
  diff  = mean abs frame difference (subject motion)
  sharp = Laplacian variance (blur)
Output JSON keyed by file stem. Thumbnails/contact sheets are still needed for content:
this score cannot see fingers, phones in frame or a missed moment.

Usage: shot_stability.py <out.json> <clip> [<clip> ...]
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys

import numpy as np

W, H, FPS = 192, 108, 10
WIN = np.outer(np.hanning(H), np.hanning(W))


def decode(path):
    for hw in (['-hwaccel', 'videotoolbox'], []):
        r = subprocess.run(['ffmpeg', '-v', 'error', *hw, '-i', path, '-an', '-vf',
                            f'fps={FPS},scale={W}:{H},format=gray', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
        if r.returncode == 0 and r.stdout:
            raw = np.frombuffer(r.stdout, np.uint8); n = raw.size // (W * H)
            return raw[:n * W * H].reshape(n, H, W).astype(np.float32)
    raise RuntimeError(f'decode failed: {path}')


def shift(a, b):
    R = np.fft.fft2(a * WIN) * np.conj(np.fft.fft2(b * WIN)); R /= np.abs(R) + 1e-9
    y, x = np.unravel_index(np.argmax(np.fft.ifft2(R).real), (H, W))
    return (x - W if x > W // 2 else x), (y - H if y > H // 2 else y)


def analyse(path):
    fr = decode(path); n = len(fr)
    dx = np.zeros(n); dy = np.zeros(n); diff = np.zeros(n); sharp = np.zeros(n)
    for i in range(n):
        f = fr[i]
        sharp[i] = (-4 * f[1:-1, 1:-1] + f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:]).var()
        if i:
            dx[i], dy[i] = shift(f, fr[i - 1]); diff[i] = np.abs(f - fr[i - 1]).mean()
    k = np.ones(FPS) / FPS
    jit = np.hypot(dx - np.convolve(dx, k, 'same'), dy - np.convolve(dy, k, 'same'))
    pan = np.hypot(np.convolve(dx, k, 'same'), np.convolve(dy, k, 'same'))
    return os.path.splitext(os.path.basename(path))[0], dict(
        path=os.path.abspath(path), fps=FPS, n=n, jit=jit.round(2).tolist(), pan=pan.round(2).tolist(),
        diff=diff.round(2).tolist(), sharp=sharp.round(1).tolist())


def main(out, clips):
    res = {}
    with concurrent.futures.ProcessPoolExecutor(4) as ex:
        for stem, d in ex.map(analyse, clips):
            res[stem] = d
            print(stem, d['n'] / FPS, 's', 'jit median %.2f' % np.median(d['jit']), flush=True)
    json.dump(res, open(out, 'w'))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
