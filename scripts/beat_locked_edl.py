#!/usr/bin/env python3
"""Turn an editorial shot list into a frame-exact, beat-locked EDL.

Shot list CSV columns: path,search_in,search_out,bars,note[,ambience][,beauty]
  bars     : length in bars (1 bar = 4 beats). 0.5 = half-bar accent (lands on beat 3),
             2 = two bars, ... ; `END` = last shot, runs to --end.
  ambience : optional per-shot raw-audio gain (default --ambience; use 0 for talking/selfie).
  beauty   : 1 = protagonist face on screen -> face_beauty.py retouch + face-safe grade.
  Any other extra column is copied into the EDL unchanged.
Every cut is placed on a measured downbeat from beat_grid.py (half bars on measured beats),
floored to the frame at/just before the kick attack, so music and picture stay locked even if
the tempo wanders. Shot durations are integer frames; the in-point is the most stable window
inside [search_in, search_out] according to shot_stability.py.

Usage: beat_locked_edl.py <shots.csv> <beats.json> <stability.json> <out_prefix>
       --end <seconds> [--fps F] [--music-offset 0] [--ambience 0.1]
--fps defaults to the frame rate of the first source clip. Relative `path`s are resolved
against the folder of shots.csv.
--music-offset: timeline time at which BGM second 0 plays (e.g. after a cold-open preview).
Writes <out_prefix>.json and <out_prefix>.csv (first five columns = project EDL format).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess

import numpy as np

BASE = {'path', 'search_in', 'search_out', 'bars', 'note', 'ambience'}


def main():
    ap = argparse.ArgumentParser()
    for a in ('shots', 'beats', 'stability', 'out_prefix'):
        ap.add_argument(a)
    ap.add_argument('--fps', type=int)
    ap.add_argument('--end', type=float, required=True)
    ap.add_argument('--music-offset', type=float, default=0.0)
    ap.add_argument('--ambience', type=float, default=0.1)
    a = ap.parse_args()
    b = json.load(open(a.beats)); stab = json.load(open(a.stability))
    beats = np.array(b['beats']) + a.music_offset
    down = beats[b['downbeat_phase']::4]
    half = beats[b['downbeat_phase']::2]
    shots = list(csv.DictReader(open(a.shots, encoding='utf-8')))
    base = os.path.dirname(os.path.abspath(a.shots))
    for s in shots:
        s['path'] = os.path.normpath(os.path.join(base, os.path.expanduser(s['path'])))
    if not a.fps:
        r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate',
                            '-of', 'json', shots[0]['path']], capture_output=True, text=True).stdout
        n, d = json.loads(r)['streams'][0]['r_frame_rate'].split('/'); a.fps = round(int(n) / int(d))
    t = 0.0; bar = 0.0; rows = []
    for k, s in enumerate(shots):
        if s['bars'].strip().upper() == 'END':
            t1 = a.end
        else:
            bar += float(s['bars'])
            t1 = down[int(bar)] if bar == int(bar) else half[int(bar * 2)]
        f0 = 0 if k == 0 else int(np.floor(t * a.fps + 1e-6)); f1 = int(np.floor(t1 * a.fps + 1e-6))
        n = f1 - f0; dur = n / a.fps
        st = stab[os.path.splitext(os.path.basename(s['path']))[0]]
        jit = np.array(st['jit']); sfps = st['fps']; need = int(round(dur * sfps))
        lo, hi = float(s['search_in']), float(s['search_out']); best = None
        for i in range(int(lo * sfps), int(hi * sfps) - need + 1):
            seg = jit[i:i + need]; cost = seg.mean() + 0.4 * np.percentile(seg, 90)
            if best is None or cost < best[0]:
                best = (cost, i / sfps)
        if best is None:
            raise SystemExit(f'shot {k + 1}: window {lo}-{hi}s shorter than {dur:.2f}s')
        amb = s.get('ambience') or ''
        rows.append(dict(order=k + 1, path=s['path'], start=round(best[1], 3), duration=round(dur, 4),
                         audio_gain=float(amb) if amb.strip() else a.ambience, frames=n,
                         timeline_in=round(f0 / a.fps, 3), timeline_out=round(f1 / a.fps, 3),
                         bars=s['bars'], jitter=round(float(best[0]), 3), note=s['note'],
                         **{k: v for k, v in s.items() if k not in BASE}))  # pass-through, e.g. beauty
        t = t1
    json.dump(rows, open(a.out_prefix + '.json', 'w'), ensure_ascii=False, indent=1)
    with open(a.out_prefix + '.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(f"{r['order']:3d} {r['timeline_in']:7.2f}-{r['timeline_out']:7.2f} {r['duration']:5.2f}s "
              f"@{r['start']:7.2f} j{r['jitter']:.2f} {r['note']}")


if __name__ == '__main__':
    main()
