#!/usr/bin/env python3
"""Frame-exact render of a beat_locked_edl.py EDL at the SOURCE spec -- never below the footage.

Output spec (hard rule): resolution, frame rate and bit depth of the source footage.
  - default size = largest source width x height in the EDL (e.g. 3840x2160); fps = the most
    common source frame rate (override with --fps); 10-bit HEVC (libx265 main10, CRF 16, hvc1, bt709).
  - the picture is encoded ONCE: each shot is graded in 16-bit RGB and encoded to its final
    codec; the video fade-out is baked into the last shot; segments are concatenated and muxed
    with stream copy. No intermediate 8-bit or second lossy pass.
  - --width/--height smaller than the source are refused unless --allow-downscale (only when the
    user explicitly asks for a smaller delivery file -- write it as a separate file).

Video: each shot is exactly `frames` frames (input-side seek). Ambience: per-shot raw audio at
`audio_gain` with 30 ms fades, concatenated as PCM (sample exact). BGM: from --music-offset at full
level -- do NOT fade in when the song opens on a kick, a fade-in erases the first downbeats.

Look: --adaptive-grade measures every shot and scales the warm grade down on bright/warm shots
and faces (adaptive_grade.py); rows with beauty=1 go through face_beauty.py (needs --detector,
the compiled detect_faces.swift). --grade-file applies one fixed filter chain to every shot
(it must not contain 8-bit-only filters such as eq).

Usage: render_beat_locked.py <edl.json> <bgm> <out.mp4> <work_dir>
       [--adaptive-grade | --grade-file f] [--detector bin] [--width W --height H] [--fps F]
       [--bgm-gain 0.5] [--music-offset 0] [--music-fade-from T] [--video-fade 1.5]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adaptive_grade  # noqa: E402
from face_beauty import DEFAULT_ENC  # noqa: E402


def probe(path):
    st = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                    'stream=width,height,r_frame_rate,pix_fmt', '-of', 'json', path],
                                   capture_output=True, text=True).stdout)['streams'][0]
    n, d = st['r_frame_rate'].split('/')
    return int(st['width']), int(st['height']), round(int(n) / int(d)), st['pix_fmt']


def main():
    ap = argparse.ArgumentParser()
    for a in ('edl', 'bgm', 'out', 'work'):
        ap.add_argument(a)
    ap.add_argument('--grade-file'); ap.add_argument('--adaptive-grade', action='store_true')
    ap.add_argument('--detector'); ap.add_argument('--width', type=int); ap.add_argument('--height', type=int)
    ap.add_argument('--allow-downscale', action='store_true'); ap.add_argument('--fps', type=int)
    ap.add_argument('--bgm-gain', type=float, default=0.5); ap.add_argument('--music-offset', type=float, default=0)
    ap.add_argument('--music-fade-from', type=float); ap.add_argument('--video-fade', type=float, default=1.5)
    a = ap.parse_args()
    edl = json.load(open(a.edl)); work = os.path.abspath(a.work); os.makedirs(work, exist_ok=True)
    fixed = (open(a.grade_file).read().strip() + ',') if a.grade_file else ''
    if 'eq=' in fixed:
        raise SystemExit('grade file uses eq (8-bit only) -- would drop 10-bit sources to 8-bit')
    specs = {p: probe(p) for p in dict.fromkeys(r['path'] for r in edl)}
    sw = max(s[0] for s in specs.values()); sh = max(s[1] for s in specs.values())
    fps_all = [s[2] for s in specs.values()]; sfps = max(set(fps_all), key=fps_all.count)
    W, H, F = a.width or sw, a.height or sh, a.fps or sfps
    if (W < sw or H < sh) and not a.allow_downscale:
        raise SystemExit(f'refusing {W}x{H} < source {sw}x{sh}: export at source resolution (or pass --allow-downscale)')
    if F < max(fps_all):
        print(f'WARNING: output {F} fps is below some sources ({sorted(set(fps_all))}); pass --fps to change', flush=True)
    print(f'output spec: {W}x{H} @{F}fps, 10-bit HEVC (sources: {sorted(set((s[0], s[1], s[2], s[3]) for s in specs.values()))})',
          flush=True)
    looks = []; last = edl[-1]['order']

    def seg(r):
        v = f"{work}/v{r['order']:03d}.mp4"; w = f"{work}/a{r['order']:03d}.wav"; d = r['frames'] / F
        face = str(r.get('beauty', '')).strip() in ('1', 'true', 'yes')
        grade = fixed
        if a.adaptive_grade:
            st = adaptive_grade.measure(r['path'], r['start'], d); g, k = adaptive_grade.grade(st, face)
            grade = g + ','; looks.append(dict(order=r['order'], warm_k=round(k, 3), **{x: round(y, 3) for x, y in st.items()}))
        if r['order'] == last and a.video_fade > 0:  # bake the fade into the last shot -> final mux is a copy
            grade += f'fade=t=out:st={max(d - a.video_fade, 0):.3f}:d={a.video_fade},'
        if face:
            if not a.detector:
                raise SystemExit('beauty=1 needs --detector (compile detect_faces.swift)')
            subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'face_beauty.py'),
                            r['path'], str(r['start']), str(r['frames']), v, '--detector', a.detector,
                            '--width', str(W), '--height', str(H), '--fps', str(F), '--grade', grade.rstrip(','),
                            '--enc', json.dumps(DEFAULT_ENC)], check=True)
        else:
            subprocess.run(['ffmpeg', '-v', 'error', '-ss', f"{r['start']:.3f}", '-i', r['path'], '-frames:v', str(r['frames']),
                            '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},'
                                   f'setsar=1,fps={F},{grade}scale=out_color_matrix=bt709:out_range=tv,format=yuv420p10le',
                            '-an', *DEFAULT_ENC, '-video_track_timescale', str(F * 1000), '-y', v], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', f"{r['start']:.3f}", '-i', r['path'], '-vn', '-af',
                        f"aresample=48000,atrim=0:{d:.4f},afade=t=in:d=0.03,afade=t=out:st={d - 0.03:.4f}:d=0.03,"
                        f"volume={float(r['audio_gain'])},apad=whole_dur={d:.4f}",
                        '-ac', '2', '-c:a', 'pcm_s16le', '-y', w], check=True)
        print('shot', r['order'], 'done', flush=True)
        return v, w

    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        parts = list(ex.map(seg, edl))
    if looks:
        json.dump(sorted(looks, key=lambda x: x['order']), open(f'{work}/looks.json', 'w'), indent=1)
    for i, key in enumerate('va'):
        open(f'{work}/{key}.txt', 'w').write(''.join(f"file '{p[i]}'\n" for p in parts))
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', f'{work}/v.txt', '-c', 'copy',
                    '-tag:v', 'hvc1', '-y', f'{work}/video.mp4'], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', f'{work}/a.txt', '-c', 'copy',
                    '-y', f'{work}/amb.wav'], check=True)
    T = edl[-1]['timeline_out']; fade_from = a.music_fade_from if a.music_fade_from is not None else T - 3
    delay = int(round(a.music_offset * 1000))
    fc = (f"[2:a]aresample=48000,adelay={delay}|{delay},atrim=0:{T},volume={a.bgm_gain},"
          f"afade=t=out:st={fade_from}:d={T - fade_from:.3f}[m];"
          f"[1:a][m]amix=inputs=2:duration=longest:normalize=0,atrim=0:{T}[aout]")
    subprocess.run(['ffmpeg', '-v', 'error', '-i', f'{work}/video.mp4', '-i', f'{work}/amb.wav', '-i', a.bgm,
                    '-filter_complex', fc, '-map', '0:v', '-map', '[aout]', '-c:v', 'copy', '-tag:v', 'hvc1',
                    '-c:a', 'aac', '-b:a', '320k', '-movflags', '+faststart', '-t', f'{T}', '-y', a.out], check=True)
    print('FINAL', a.out)


if __name__ == '__main__':
    main()
