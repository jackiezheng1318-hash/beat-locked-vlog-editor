#!/usr/bin/env python3
"""Burn optional captions onto a finished video: small place/shop labels + a big opening title.

Two caption kinds (field "kind" in captions.json):
  label  (default) place / shop / time-log line, ~5.5% of frame height, centred at 82% height,
         0.1 s fade in/out, no pop -- quiet, sits under the picture
  title  opening title, ~10% of frame height, centred in frame, short pop-in
         (0.7 -> 1.04 -> 1.0) and 0.15 s fade out; place it on the first bars of the video

Look: white text thickened with a white stroke, thin black outline (CapCut / 剪映-like).
Font: --font <file> [--font-index N]; otherwise the first rounded/bold CJK font found:
macOS Yuanti SC Bold (downloadable system asset) -> PingFang SC Semibold -> Hiragino Sans GB W6,
Linux Noto Sans CJK Bold, Windows Microsoft YaHei Bold.
No drawtext needed: captions are PIL-rendered PNG sequences overlaid at their time range.
Picture cuts are untouched and audio is stream-copied.

captions.json: [{"start": 0.0, "end": 3.76, "text": "Weekend city walk", "kind": "title"},
                {"start": 31.88, "end": 33.74, "text": "West Nanjing Road"}, ...]
  optional per item: "y" (0-1 centre height), "size" (fraction of frame height)
Use the shot's cut times so captions enter/leave on the beat. Only write a place name that is
readable on a sign in the frame.

Usage: burn_captions.py <in.mp4> <captions.json> <out.mp4> [--font path] [--font-index N]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONTS = [(p, 2) for p in glob.glob('/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/Yuanti.ttc')] + \
        [(p, 11) for p in glob.glob('/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc')] + \
        [('/System/Library/Fonts/Hiragino Sans GB.ttc', 2),
         ('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 2),
         ('/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc', 2),
         ('C:/Windows/Fonts/msyhbd.ttc', 0)]
KINDS = {  # size = glyph em as fraction of frame height
    'label': dict(size=0.055, y=0.82, bold=0.015, stroke=0.08, pop=False, fade_in=0.10, fade_out=0.10),
    'title': dict(size=0.10, y=0.50, bold=0.02, stroke=0.07, pop=True, fade_in=0.08, fade_out=0.15),
}


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height,r_frame_rate', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout
    w, h, r = out.strip().split(','); n, d = r.split('/')
    return int(w), int(h), round(int(n) / int(d))


def card(text, size, bold_frac, stroke_frac, font):
    f = ImageFont.truetype(font[0], size, index=font[1])
    bold = max(1, round(size * bold_frac)); stroke = bold + max(2, round(size * stroke_frac))
    l, t, r, b = ImageDraw.Draw(Image.new('RGBA', (1, 1))).textbbox((0, 0), text, font=f, stroke_width=stroke)
    pad = stroke + 2; im = Image.new('RGBA', (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.text((pad - l, pad - t), text, font=f, fill='black', stroke_width=stroke, stroke_fill='black')
    d.text((pad - l, pad - t), text, font=f, fill='white', stroke_width=bold, stroke_fill='white')
    return im


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('captions'); ap.add_argument('out')
    ap.add_argument('--font'); ap.add_argument('--font-index', type=int, default=0)
    a = ap.parse_args()
    if a.font:
        font = (a.font, a.font_index)
    else:
        font = next((f for f in FONTS if os.path.exists(f[0])), None)
        if font is None:
            raise SystemExit('no CJK font found -- pass --font /path/to/font.ttf')
    W, H, F = probe(a.src); caps = json.load(open(a.captions))
    tmp = tempfile.mkdtemp(prefix='captions-'); inputs = []; chain = []; last = '0:v'
    for i, c in enumerate(caps):
        k = dict(KINDS[c.get('kind', 'label')]); k.update({x: c[x] for x in ('y', 'size') if x in c})
        base = card(c['text'], int(k['size'] * H), k['bold'], k['stroke'], font)
        n = int(round((c['end'] - c['start']) * F)); d = f'{tmp}/c{i}'; os.makedirs(d)
        bw, bh = base.size; cw, ch = int(bw * 1.05) + 2, int(bh * 1.05) + 2
        for j in range(n):
            t = j / F; rest = (n - 1 - j) / F
            s = 1.0
            if k['pop']:
                s = 0.7 + 0.34 * min(t / 0.12, 1) if t < 0.12 else 1.04 - 0.04 * min((t - 0.12) / 0.08, 1)
            alpha = max(0.0, min(1.0, t / k['fade_in'], rest / k['fade_out']))
            im = base if s == 1.0 else base.resize((max(1, int(bw * s)), max(1, int(bh * s))), Image.LANCZOS)
            if alpha < 1:
                im = im.copy(); im.putalpha(im.getchannel('A').point(lambda v: int(v * alpha)))
            frame = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
            frame.paste(im, ((cw - im.width) // 2, (ch - im.height) // 2), im); frame.save(f'{d}/{j:04d}.png')
        x = (W - cw) // 2; y = int(k['y'] * H - ch / 2)
        inputs += ['-framerate', str(F), '-itsoffset', f"{c['start']:.3f}", '-i', f'{d}/%04d.png']
        chain.append(f"[{last}][{i + 1}:v]overlay={x}:{y}:eof_action=pass:enable='between(t,{c['start']:.3f},{c['end']:.3f})'[o{i}]")
        last = f'o{i}'
    subprocess.run(['ffmpeg', '-v', 'error', '-i', a.src, *inputs, '-filter_complex', ';'.join(chain), '-map', f'[{last}]',
                    '-map', '0:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                    '-c:a', 'copy', '-movflags', '+faststart', '-y', a.out], check=True)
    print('captions burned:', len(caps), 'font:', os.path.basename(font[0]), '->', a.out)


if __name__ == '__main__':
    main()
