#!/usr/bin/env python3
"""Acceptance check for beat sync, measured from the finished video itself.

1. Cuts are detected from pixels (scdet, threshold 12) -- not trusted from the EDL.
2. The BGM is located inside the mix by onset-envelope cross-correlation on a window in the
   middle of the video (adapts to the video length); --max-offset bounds |video_time - bgm_time|.
3. Each cut is compared with the nearest measured beat / downbeat from beat_grid.py.

Gate used by the skill: >= 90% of detected cuts within ±40 ms of a beat. Negative error =
cut lands before the kick (0-20 ms early is the intended placement).
Note: always decode from 0 and slice; input-side -ss on AAC/MP3 moves audio by tens of ms.

Usage: verify_beat_sync.py <video> <beats.json> <bgm_audio> [--max-offset 20]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess

import numpy as np

SR, BLK = 11025, 11  # envelope block = 11 samples (0.998 ms) -- convert with BLK / SR, not 1 ms


def envelope(path, start, dur):
    x = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(SR),
                                      '-f', 's16le', '-'], capture_output=True).stdout, np.int16).astype(float)
    x = x[int(start * SR):int((start + dur) * SR)]
    e = np.abs(x[:len(x) // BLK * BLK]).reshape(-1, BLK).mean(1)
    d = np.maximum(0, np.diff(e, prepend=e[0])); return d - d.mean()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('video'); ap.add_argument('beats'); ap.add_argument('bgm')
    ap.add_argument('--max-offset', type=float, default=20.0); a = ap.parse_args()
    b = json.load(open(a.beats)); bt = np.array(b['beats']); down = np.array(b['downbeats'])
    err = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', a.video, '-vf', 'scale=320:-2,scdet=threshold=12',
                          '-an', '-f', 'null', '-'], capture_output=True, text=True).stderr
    cuts = np.array(sorted(float(x) for x in re.findall(r'lavfi\.scd\.time:\s*([0-9.]+)', err)))
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.video],
                               capture_output=True, text=True).stdout)
    ms, ml = min(20.0, 0.2 * dur), min(30.0, 0.6 * dur)  # analysis window inside the video
    mix = envelope(a.video, ms, ml)
    lo = max(0.0, ms - a.max_offset); hi = ms + a.max_offset  # candidate BGM times for video time ms
    ref = envelope(a.bgm, lo, hi - lo + ml + 1)
    n_lag = max(1, min(int((hi - lo) * SR / BLK), len(ref) - len(mix)))
    L = int(np.argmax([np.dot(mix, ref[i:i + len(mix)]) for i in range(n_lag)]))
    offset = ms - (lo + L * BLK / SR)  # video_time - bgm_time
    cb = cuts - offset
    e_b = np.array([c - bt[np.argmin(abs(bt - c))] for c in cb]) * 1000
    e_d = np.array([c - down[np.argmin(abs(down - c))] for c in cb]) * 1000
    n = len(cuts); ok = int((abs(e_b) <= 40).sum())
    res = dict(video=a.video, detected_cuts=n, bgm_offset_s=round(float(offset), 3),
               median_abs_error_ms=round(float(np.median(abs(e_b))), 1) if n else None,
               within_40ms_of_beat=f'{ok}/{n}', within_40ms_of_downbeat=f'{int((abs(e_d) <= 40).sum())}/{n}',
               gate_pass=bool(n and ok / n >= 0.9),
               per_cut_ms=[[round(float(c), 3), int(e)] for c, e in zip(cuts, e_b)])
    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main()
