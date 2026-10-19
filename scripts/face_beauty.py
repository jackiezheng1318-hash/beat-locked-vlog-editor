#!/usr/bin/env python3
"""Natural skin retouch for the main person's face shots (selfie vlogs): removes blemishes and
evens skin tone while keeping eyes, brows, glasses and lips sharp. macOS only (Vision framework).

Pipeline for one shot:
  1. decode the shot (exact frame count) to RGB at output size
  2. macOS Vision (detect_faces.swift) finds face box + landmarks on every 4th frame,
     interpolated in between
  3. mask = feathered face ellipse (forehead..chin) x skin-chroma (YCrCb) x NOT(eyes, brows,
     glasses, lips, nostril edge) -> only skin is touched, features stay sharp
  4. edge-preserving smoothing (self-guided filter, radius ~3% of face width) blended at
     --strength, plus ~25% of fine texture added back so skin doesn't look plastic
  5. inside the mask: +3% brightness and a small yellow->neutral shift (faces in strong sun
     read too yellow after a warm grade)
  6. frames are piped to ffmpeg (rgb48), which applies the per-shot grade and encodes 10-bit

Quality: works at the SOURCE resolution (default) in 16-bit RGB, streaming one frame at a time
(a 4K clip never sits in memory), detection runs on a separate 960-px pass; output is encoded
once with the same 10-bit HEVC settings as render_beat_locked.py (--enc, JSON arg list).

Usage: face_beauty.py <src> <start> <frames> <out.mp4> --detector <detect_faces binary>
       [--width W --height H] [--fps F] [--grade "<ffmpeg filters>"] [--strength 0.85]
       [--enc '<json list of ffmpeg encoder args>'] [--preview out.jpg]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw


def box(a, r):
    """Mean filter of radius r along both axes (cumsum, any float array HxW[xC])."""
    k = 2 * r + 1
    p = np.pad(a, ((r + 1, r), (r + 1, r)) + ((0, 0),) * (a.ndim - 2), mode='edge')
    c = p.cumsum(0); c = c[k:] - c[:-k]
    c = c.cumsum(1); c = c[:, k:] - c[:, :-k]
    return c / (k * k)


def guided(I, r, eps):
    m = box(I, r); v = box(I * I, r) - m * m
    a = v / (v + eps); b = m - a * m
    return box(a, r) * I + box(b, r)


def skin_mask(rgb):
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    Y = 0.299 * R + 0.587 * G + 0.114 * B
    Cr = (R - Y) * 0.713 + 0.5; Cb = (B - Y) * 0.564 + 0.5
    s = np.clip((Cr - 0.52) / 0.03, 0, 1) * np.clip((0.70 - Cr) / 0.03, 0, 1)
    s *= np.clip((Cb - 0.33) / 0.03, 0, 1) * np.clip((0.53 - Cb) / 0.03, 0, 1)
    return s * np.clip((Y - 0.12) / 0.08, 0, 1)


def interp_faces(det, n, step):
    """det: {frame_idx: face or None}; returns per-frame face (box + regions) or None."""
    keys = sorted(k for k, v in det.items() if v); out = [None] * n
    if not keys:
        return out
    for i in range(n):
        lo = max([k for k in keys if k <= i], default=None); hi = min([k for k in keys if k >= i], default=None)
        if lo is None or hi is None:
            k = lo if hi is None else hi
            out[i] = det[k] if abs(k - i) <= 2 * step else None; continue
        if hi - lo > 4 * step:  # face lost for a while: don't guess
            continue
        w = 0 if hi == lo else (i - lo) / (hi - lo); A, B = det[lo], det[hi]
        f = {'box': [(1 - w) * x + w * y for x, y in zip(A['box'], B['box'])], 'regions': {}}
        for key, pts in A['regions'].items():
            if key in B['regions'] and len(B['regions'][key]) == len(pts):
                f['regions'][key] = [[(1 - w) * p[0] + w * q[0], (1 - w) * p[1] + w * q[1]]
                                     for p, q in zip(pts, B['regions'][key])]
        out[i] = f
    return out


def face_mask(face, W, H):
    x, y, w, h = face['box']; X0, Y0 = int(max(0, (x - 0.35 * w) * W)), int(max(0, (y - 0.45 * h) * H))
    X1, Y1 = int(min(W, (x + 1.35 * w) * W)), int(min(H, (y + 1.25 * h) * H))
    if X1 - X0 < 16 or Y1 - Y0 < 16:
        return None
    cw, ch = X1 - X0, Y1 - Y0; sc = 4  # draw at 1/4 res then upsample
    m = Image.new('L', (cw // sc + 1, ch // sc + 1), 0); d = ImageDraw.Draw(m)
    cx, cy = (x + w / 2) * W - X0, (y + h * 0.42) * H - Y0  # centre shifted up to cover forehead
    d.ellipse([(cx - 0.56 * w * W) / sc, (cy - 0.78 * h * H) / sc, (cx + 0.56 * w * W) / sc, (cy + 0.62 * h * H) / sc], fill=255)
    for key, grow in (('leftEye', 0.9), ('rightEye', 0.9), ('leftEyebrow', 0.5), ('rightEyebrow', 0.5),
                      ('outerLips', 0.35)):
        pts = face['regions'].get(key)
        if not pts:
            continue
        P = np.array([[p[0] * W - X0, p[1] * H - Y0] for p in pts]); c = P.mean(0)
        P = c + (P - c) * (1 + grow)
        d.polygon([tuple(q / sc) for q in P], fill=0)
    if not face['regions'].get('leftEye'):  # no landmarks: protect eye band generically
        d.rectangle([(x - 0.05) * W / sc, (y + 0.25 * h) * H / sc, (x + w + 0.05) * W / sc, (y + 0.5 * h) * H / sc], fill=0)
    a = np.asarray(m.resize((cw, ch), Image.BILINEAR), np.float32) / 255
    r = max(2, int(0.04 * w * W)); a = box(box(a, r), r)
    return (X0, Y0, X1, Y1), a, w * W


DEFAULT_ENC = ['-c:v', 'libx265', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p10le', '-profile:v', 'main10',
               '-tag:v', 'hvc1', '-x265-params', 'log-level=error',
               '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709']


def retouch(frame, face, strength):
    """frame: HxWx3 uint16 (full range). Returns a new uint16 frame."""
    H, W, _ = frame.shape; fm = face_mask(face, W, H)
    if fm is None:
        return frame
    (X0, Y0, X1, Y1), ell, fw = fm
    crop = frame[Y0:Y1, X0:X1].astype(np.float32) / 65535
    mask = ell * box(skin_mask(crop), 3)
    r = max(5, int(fw * 0.045)); smooth = np.stack([guided(crop[..., c], r, 0.012) for c in range(3)], -1)
    detail = crop - box(crop, 1)
    res = smooth + 0.15 * detail
    res = res * 1.03; res[..., 2] *= 1.035; res[..., 0] *= 0.99  # lift + pull yellow toward neutral
    m = (strength * mask)[..., None]
    out = frame.copy(); out[Y0:Y1, X0:X1] = np.clip((crop * (1 - m) + res * m) * 65535, 0, 65535).astype(np.uint16)
    return out


def probe_fps(path):
    st = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                    'stream=r_frame_rate', '-of', 'json', path], capture_output=True, text=True).stdout)
    n, d = st['streams'][0]['r_frame_rate'].split('/')
    return round(int(n) / int(d))


def probe_size(path):
    st = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                    'stream=width,height', '-of', 'json', path], capture_output=True, text=True).stdout)
    return int(st['streams'][0]['width']), int(st['streams'][0]['height'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('start', type=float); ap.add_argument('frames', type=int); ap.add_argument('out')
    ap.add_argument('--detector', required=True); ap.add_argument('--width', type=int); ap.add_argument('--height', type=int)
    ap.add_argument('--fps', type=int); ap.add_argument('--grade', default='')
    ap.add_argument('--strength', type=float, default=0.85); ap.add_argument('--step', type=int, default=4)
    ap.add_argument('--enc', default=json.dumps(DEFAULT_ENC)); ap.add_argument('--preview')
    a = ap.parse_args(); N = a.frames
    W, H = (a.width, a.height) if a.width and a.height else probe_size(a.src)
    if not a.fps:
        a.fps = probe_fps(a.src)
    vf = (f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos:in_color_matrix=bt709,'
          f'crop={W}:{H},setsar=1,fps={a.fps}')  # RGB round trip pinned to bt709 so colours match other shots
    with tempfile.TemporaryDirectory() as tmp:  # pass 1: detection on small frames
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{a.start:.3f}', '-i', a.src, '-vf',
                        f"{vf},trim=end_frame={N},select='not(mod(n\\,{a.step}))',scale=960:-2", '-fps_mode', 'passthrough',
                        '-q:v', '3', f'{tmp}/%05d.jpg'], check=True)
        subprocess.run([a.detector, tmp, f'{tmp}/faces.json'], check=True, capture_output=True)
        found = json.load(open(f'{tmp}/faces.json'))
    det = {}
    for name, faces in found.items():
        faces = [f for f in faces if f['box'][2] > 0.06]  # ignore tiny background faces
        det[(int(name[:5]) - 1) * a.step] = max(faces, key=lambda f: f['box'][2] * f['box'][3]) if faces else None
    per = interp_faces(det, N, a.step)
    grade = (a.grade.rstrip(',') + ',') if a.grade else ''
    dec = subprocess.Popen(['ffmpeg', '-v', 'error', '-ss', f'{a.start:.3f}', '-i', a.src, '-frames:v', str(N), '-vf', vf,
                            '-f', 'rawvideo', '-pix_fmt', 'rgb48le', '-'], stdout=subprocess.PIPE)
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb48le', '-s', f'{W}x{H}', '-r', str(a.fps),
                            '-i', '-', '-vf', f'{grade}scale=out_color_matrix=bt709:out_range=tv,format=yuv420p10le',
                            *json.loads(a.enc), '-video_track_timescale', str(a.fps * 1000), '-y', a.out], stdin=subprocess.PIPE)
    done = n = 0; size = W * H * 6
    for i in range(N):
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        f = np.frombuffer(buf, '<u2').reshape(H, W, 3)
        g = retouch(f, per[i], a.strength) if per[i] else f
        done += per[i] is not None; n += 1
        if a.preview and i == N // 2 and per[i]:
            x, y, w, h = per[i]['box']; bx = [int((x - 0.3 * w) * W), int((y - 0.4 * h) * H), int((x + 1.3 * w) * W), int((y + 1.3 * h) * H)]
            A = Image.fromarray((f >> 8).astype(np.uint8)).crop(bx); B = Image.fromarray((g >> 8).astype(np.uint8)).crop(bx)
            Pv = Image.new('RGB', (A.width * 2, A.height)); Pv.paste(A, (0, 0)); Pv.paste(B, (A.width, 0)); Pv.save(a.preview, quality=92)
        enc.stdin.write(g.astype('<u2').tobytes())
    dec.wait(); enc.stdin.close(); enc.wait()
    print(f'{os.path.basename(a.out)}: {n}/{N} frames {W}x{H}, retouched {done}, detections {sum(1 for v in det.values() if v)}/{len(det)}')


if __name__ == '__main__':
    main()
