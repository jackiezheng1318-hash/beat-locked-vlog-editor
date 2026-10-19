#!/usr/bin/env python3
"""First / middle / last frame of every EDL shot, straight from the raw source, one row per shot.

Run it after beat_locked_edl.py and BEFORE rendering. Handheld POV footage is full of fingers,
arms, phones and whip-pans at the edges of a window; these only show up at the in/out frames.
Fix a bad shot by narrowing its search window in shots.csv and rebuilding the EDL.

Usage: shot_review.py <edl.json> <out_prefix> [--per 16]   -> <out_prefix>-1.jpg, -2.jpg ...
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONTS = ['/System/Library/Fonts/Hiragino Sans GB.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
         '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc', 'C:/Windows/Fonts/msyh.ttc']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('edl'); ap.add_argument('out'); ap.add_argument('--per', type=int, default=16)
    a = ap.parse_args(); edl = json.load(open(a.edl))
    font = next((ImageFont.truetype(f, 18) for f in FONTS if os.path.exists(f)), ImageFont.load_default())
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(r, tag, r['start'] + off) for r in edl
                for tag, off in (('a', 0.04), ('b', r['duration'] / 2), ('c', max(r['duration'] - 0.06, 0)))]

        def grab(j):
            r, tag, t = j; p = f"{tmp}/{r['order']:03d}{tag}.jpg"
            subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', r['path'], '-frames:v', '1',
                            '-vf', 'scale=384:216:force_original_aspect_ratio=decrease,pad=384:216:(ow-iw)/2:(oh-ih)/2',
                            '-q:v', '4', '-y', p], check=True)
        with concurrent.futures.ThreadPoolExecutor(6) as ex:
            list(ex.map(grab, jobs))
        for s in range(0, len(edl), a.per):
            rows = edl[s:s + a.per]
            im = Image.new('RGB', (384 * 3 + 330, 216 * len(rows)), (18, 18, 18)); d = ImageDraw.Draw(im)
            for i, r in enumerate(rows):
                for k, tag in enumerate('abc'):
                    im.paste(Image.open(f"{tmp}/{r['order']:03d}{tag}.jpg"), (k * 384, i * 216))
                d.text((1162, i * 216 + 10), f"#{r['order']}  {r['timeline_in']:.2f}-{r['timeline_out']:.2f}s", fill='white', font=font)
                d.text((1162, i * 216 + 40), f"{os.path.basename(r['path'])[-16:]} @{r['start']:.1f}s", fill=(180, 180, 180), font=font)
                d.text((1162, i * 216 + 70), str(r.get('note', ''))[:16], fill=(250, 210, 120), font=font)
            im.save(f'{a.out}-{s // a.per + 1}.jpg', quality=80)
    print('review sheets:', (len(edl) + a.per - 1) // a.per)


if __name__ == '__main__':
    main()
