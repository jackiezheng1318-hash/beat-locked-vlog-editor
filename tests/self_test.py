#!/usr/bin/env python3
"""End-to-end self-test with synthetic media only (no real footage or music is shipped).

1. synthesises a 120 BPM drum loop (kick on beat 1 of every bar, hats on every beat)
2. synthesises 4 short 1280x720 50 fps 10-bit HEVC "camera clips" (moving test patterns)
3. runs beat_grid -> shot_stability -> beat_locked_edl -> render_beat_locked -> verify_beat_sync
4. asserts: tempo ≈ 120, first downbeat ≈ 0 s, output spec == source spec, sync gate passes

Usage: python tests/self_test.py [--keep]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, '..', 'scripts')
PY = sys.executable


def run(*args):
    r = subprocess.run(list(args), capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:]); raise SystemExit(f'FAILED: {" ".join(args[:3])}')
    return r.stdout


def main():
    keep = '--keep' in sys.argv
    w = tempfile.mkdtemp(prefix='beatlocked-selftest-')
    try:
        bgm = os.path.join(w, 'drums.wav')
        # kick: 60 Hz decaying sine on every bar start (2 s bar at 120 BPM); hat: noise burst every beat
        kick = "0.9*sin(2*PI*60*mod(t,2))*exp(-12*mod(t,2))"
        hat = "0.15*(random(0)*2-1)*exp(-60*mod(t,0.5))"
        bass = "0.25*sin(2*PI*110*t)*(0.5+0.5*sin(2*PI*0.25*t))"
        run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f"aevalsrc='{kick}+{hat}+{bass}':s=44100:d=40",
            '-ac', '2', '-y', bgm)
        clips = []
        for i, src in enumerate(['testsrc2', 'smptehdbars', 'rgbtestsrc', 'testsrc']):
            p = os.path.join(w, f'clip{i}.mp4')
            run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'{src}=s=1280x720:r=50:d=14',
                '-f', 'lavfi', '-i', 'sine=f=440:d=14', '-vf', f'hue=h={i * 70},format=yuv420p10le',
                '-c:v', 'libx265', '-x265-params', 'log-level=error', '-crf', '20', '-c:a', 'aac', '-shortest', '-y', p)
            clips.append(p)
        print('synthetic media ok')

        beats = os.path.join(w, 'beats.json')
        run(PY, f'{S}/beat_grid.py', bgm, beats)
        b = json.load(open(beats))
        assert abs(b['bpm'] - 120) < 1.0, f"bpm {b['bpm']}"
        assert b['downbeats'][0] < 0.05, f"first downbeat {b['downbeats'][0]}"
        print(f"beat_grid ok: {b['bpm']} BPM, first downbeat {b['downbeats'][0]} s")

        stab = os.path.join(w, 'stab.json')
        run(PY, f'{S}/shot_stability.py', stab, *clips)
        shots = os.path.join(w, 'shots.csv')
        with open(shots, 'w') as f:
            f.write('path,search_in,search_out,bars,note,ambience,beauty\n')
            plan = [(0, 1), (1, 1), (2, 0.5), (3, 0.5), (0, 2), (1, 1), (2, 'END')]
            for k, (c, bars) in enumerate(plan):
                f.write(f'clip{c}.mp4,{(k % 3) * 2},{(k % 3) * 2 + 7},{bars},shot {k + 1},,0\n')
        edl = os.path.join(w, 'edl')
        run(PY, f'{S}/beat_locked_edl.py', shots, beats, stab, edl, '--end', str(b['downbeats'][7] + 2))
        out = os.path.join(w, 'final.mp4')
        run(PY, f'{S}/render_beat_locked.py', edl + '.json', bgm, out, os.path.join(w, 'render'),
            '--adaptive-grade', '--music-fade-from', str(b['downbeats'][6]), '--video-fade', '1.0')
        spec = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                              'stream=width,height,r_frame_rate,pix_fmt', '-of', 'json', out))['streams'][0]
        assert (spec['width'], spec['height'], spec['r_frame_rate'], spec['pix_fmt']) == (1280, 720, '50/1', 'yuv420p10le'), spec
        print('render ok:', spec)
        v = json.loads(run(PY, f'{S}/verify_beat_sync.py', out, beats, bgm))
        print('verify:', {k: v[k] for k in ('detected_cuts', 'median_abs_error_ms', 'within_40ms_of_beat', 'gate_pass')})
        assert v['gate_pass'] and v['detected_cuts'] >= 5, v
        print('\nSELF-TEST PASSED')
    finally:
        if keep:
            print('kept:', w)
        else:
            shutil.rmtree(w, ignore_errors=True)


if __name__ == '__main__':
    main()
