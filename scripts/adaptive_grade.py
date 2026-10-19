#!/usr/bin/env python3
"""Scene-aware, per-shot adaptive grade (16-bit, no 8-bit filters).

Two levels:
1. LOOK for the whole video, chosen from the footage itself: light/weather (sunny, overcast,
   golden hour, night, indoor, snow) x season (from the clip's creation date; --south flips
   hemispheres). `suggest_look()` measures every shot and explains its choice; a human/agent
   should confirm it against the contact sheets and may override with --look / --season.
   Stats alone cannot tell "indoors" from "outdoors under an awning" (both warm, saturated, no sky),
   so the suggestion is only a hint: look at the contact sheets, decide, and for mixed footage set a
   per-shot `look` column in shots.csv (e.g. indoor shots of a business trip); empty = video look.
2. PER SHOT inside the look: warmth is scaled down on shots that are already bright or warm and
   on faces (x0.45), highlights are protected on bright shots -- so one look never over-yellows a
   sunny facade or a face.

Looks (base) and season modifiers:
  golden-sun   sunny day: warm highlights, slightly cool shadows, gentle contrast  (author-approved
               baseline from two sunny city walks; kept identical to those renders)
  overcast     flat grey light: more contrast + vibrance to bring colour back, little warmth,
               grey sky kept neutral (warming a grey sky looks dirty)
  golden-hour  low sun, footage already warm: barely add warmth, protect highlights
  night        city night: no warming, deep blacks kept, teal-ish shadows, colour lifted
  indoor       artificial light: neutralise orange cast, mild contrast
  snow         winter/snow: cool clean whites, lifted exposure, restrained colour
  season x     spring 0.8 warmth + fresh greens; summer/autumn 1.0 (approved baseline);
               winter 0.6 warmth, less vibrance

CLI:
  adaptive_grade.py <video> <start> <duration> [--face] [--look L] [--season S]   one shot -> filter
  adaptive_grade.py --suggest <edl.json> [--south]                                 whole edit -> look + reasons
Library: measure(path, start, dur) -> stats; suggest_look(stats_list, month) -> (look, season, why);
         grade(stats, face, look, season) -> (ffmpeg filter, warm k)
"""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np

# temp K (lower = warmer), base warm mix, tone curve (x, y), shadow/mid/highlight balance (r, g, b),
# whether mid/highlight warmth scales with the per-shot k, vibrance, saturation, contrast
LOOKS = {
    'golden-sun':  dict(temp=5400, mix=0.45, curve=((0, .02), (.25, .23), (.5, .52), (.75, .79), (1, .97)),
                        sh=(-.02, 0, .03), mid=(.012, .005, -.018), hi=(.03, .012, -.03), scale=True,
                        vib=.10, sat=1.03, con=1.03),
    'overcast':    dict(temp=5800, mix=0.25, curve=((0, .0), (.25, .21), (.5, .51), (.75, .81), (1, .98)),
                        sh=(-.015, 0, .02), mid=(.008, .004, -.01), hi=(0, 0, 0), scale=True,
                        vib=.18, sat=1.05, con=1.06),
    'golden-hour': dict(temp=5600, mix=0.12, curve=((0, .02), (.25, .24), (.5, .52), (.75, .78), (1, .95)),
                        sh=(-.02, 0, .025), mid=(.004, .002, -.006), hi=(.01, .004, -.01), scale=True,
                        vib=.08, sat=1.02, con=1.02),
    'night':       dict(temp=6500, mix=0.0, curve=((0, 0), (.1, .08), (.5, .5), (.9, .92), (1, .97)),
                        sh=(-.03, 0, .03), mid=(0, 0, 0), hi=(.01, .005, -.005), scale=False,
                        vib=.15, sat=1.04, con=1.02),
    'indoor':      dict(temp=6800, mix=0.25, curve=((0, .02), (.25, .24), (.5, .51), (.75, .78), (1, .97)),
                        sh=(0, 0, .01), mid=(0, 0, 0), hi=(0, 0, 0), scale=False,
                        vib=.06, sat=1.0, con=1.03),
    'snow':        dict(temp=7000, mix=0.20, curve=((0, .03), (.25, .27), (.5, .55), (.75, .81), (1, .98)),
                        sh=(-.01, 0, .03), mid=(0, 0, .005), hi=(0, 0, 0), scale=False,
                        vib=.05, sat=.95, con=1.0),
}
SEASON = {'spring': dict(warm=0.8, green=.008, vib=.02), 'summer': dict(warm=1.0, green=0, vib=0),
          'autumn': dict(warm=1.0, green=0, vib=0), 'winter': dict(warm=0.6, green=0, vib=-.02)}


def season_of(month, south=False):
    if not month:
        return 'summer'
    m = (month + 5) % 12 + 1 if south else month
    return {12: 'winter', 1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
            6: 'summer', 7: 'summer', 8: 'summer'}.get(m, 'autumn')


def clip_month(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=creation_time', '-of', 'json', path],
                         capture_output=True, text=True).stdout or '{}'
    t = json.loads(out).get('format', {}).get('tags', {}).get('creation_time', '')
    return int(t[5:7]) if len(t) >= 7 else None


def measure(path, start, dur):
    acc = {k: [] for k in ('luma', 'rb', 'highlights', 'sat', 'contrast', 'sky', 'grey_sky', 'green', 'snow')}
    for t in (start + 0.15, start + dur / 2, start + max(dur - 0.15, 0)):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', path, '-frames:v', '1', '-vf',
                              'scale=96:96,format=rgb24', '-f', 'rawvideo', '-'], capture_output=True).stdout
        if len(raw) < 96 * 96 * 3:
            continue
        f = np.frombuffer(raw[:96 * 96 * 3], np.uint8).reshape(96, 96, 3).astype(float)
        R, G, B = f[..., 0], f[..., 1], f[..., 2]
        Y = f @ [0.299, 0.587, 0.114]; mx = f.max(-1); mn = f.min(-1); S = (mx - mn) / np.maximum(mx, 1)
        top, bot = slice(0, 32), slice(48, 96)
        acc['luma'].append(Y.mean()); acc['rb'].append(R.mean() / max(B.mean(), 1))
        acc['highlights'].append((Y > 215).mean()); acc['sat'].append(S.mean()); acc['contrast'].append(Y.std())
        acc['sky'].append(((B[top] > R[top] + 20) & (B[top] > 110) & (S[top] > .2)).mean())
        acc['grey_sky'].append(((Y[top] > 150) & (S[top] < .12)).mean())
        acc['green'].append(((G > R + 8) & (G > B + 8) & (S > .2)).mean())
        acc['snow'].append(((Y[bot] > 200) & (S[bot] < .1)).mean())
    return {k: float(np.mean(v)) if v else 0.0 for k, v in acc.items()}


def suggest_look(stats, month=None, south=False):
    med = {k: float(np.median([s[k] for s in stats])) for k in stats[0]}
    season = season_of(month, south)
    why = [f'month={month} -> {season}', 'median ' + ', '.join(f'{k}={v:.2f}' for k, v in med.items())]
    if med['luma'] < 55:
        look = 'night'; why.append('very dark footage -> night')
    elif med['snow'] > 0.25 and season == 'winter':
        look = 'snow'; why.append('winter and large bright neutral ground -> snow')
    elif np.mean([s['sky'] < .03 and s['green'] < .03 and s['rb'] > 1.1 for s in stats]) > .7:
        look = 'indoor'; why.append('no sky/vegetation and a warm cast in most shots -> indoor / artificial light')
    elif med['sky'] < .05 and med['grey_sky'] > .2 and med['sat'] < .22:
        look = 'overcast'; why.append('grey bright sky, no blue, low saturation -> overcast')
    elif med['rb'] > 1.15 and med['sky'] + med['grey_sky'] > .05:
        look = 'golden-hour'; why.append('already warm with sky in frame -> golden hour, add little warmth')
    else:
        look = 'golden-sun'; why.append('blue sky / normal contrast -> sunny')
    return look, season, why


def grade(st, face=False, look='golden-sun', season='summer'):
    L, Z = LOOKS[look], SEASON[season]
    warm_f = float(np.clip(1 - (st['rb'] - 1.05) * 2.0, 0.35, 1.0))       # already warm -> add less
    bright_f = float(np.clip(1 - (st['luma'] - 115) / 150, 0.55, 1.0))   # bright sun -> add less
    k = warm_f * bright_f * (0.45 if face else 1.0) * Z['warm']
    curve = list(L['curve'])
    if st['highlights'] > 0.08 or st['luma'] > 140:                      # protect bright shots
        curve[-1] = (1, min(curve[-1][1], .95))
    c, sat = L['con'], L['sat']
    pts = ' '.join(f'{x}/{min(max((y - 0.5) * c + 0.5, 0), 1):.4f}' for x, y in curve)
    lr, lg, lb = 0.2126 * (1 - sat), 0.7152 * (1 - sat), 0.0722 * (1 - sat)
    mix = (f'colorchannelmixer=rr={lr + sat:.5f}:rg={lg:.5f}:rb={lb:.5f}:gr={lr:.5f}:gg={lg + sat:.5f}:gb={lb:.5f}:'
           f'br={lr:.5f}:bg={lg:.5f}:bb={lb + sat:.5f}')
    w = k if L['scale'] else 1.0
    (sr, sg, sb), (mr, mg, mb), (hr, hg, hb) = L['sh'], L['mid'], L['hi']
    vib = max(0.0, (0.04 if face else L['vib']) + Z['vib'])
    chain = ['format=gbrp16le']
    if L['mix'] > 0:
        chain.append(f"colortemperature=temperature={L['temp']}:mix={L['mix'] * w:.3f}:pl=0.5")
    chain += [f"curves=master='{pts}'",
              f"colorbalance=rs={sr}:gs={sg}:bs={sb}:rm={mr * w:.4f}:gm={mg + Z['green']:.4f}:bm={mb * w:.4f}:"
              f"rh={hr * w:.4f}:gh={hg * w:.4f}:bh={hb * w:.4f}",
              f"vibrance=intensity={vib:.3f}:rbal=0.9:bbal=1.0", mix]
    return ','.join(chain), k


if __name__ == '__main__':
    argv = sys.argv
    if len(argv) >= 3 and argv[1] == '--suggest':
        edl = json.load(open(argv[2]))
        stats = [measure(r['path'], r['start'], r['duration']) for r in edl]
        look, season, why = suggest_look(stats, clip_month(edl[0]['path']), '--south' in argv)
        print(json.dumps(dict(look=look, season=season, why=why), ensure_ascii=False, indent=1))
    elif len(argv) >= 4:
        s = measure(argv[1], float(argv[2]), float(argv[3]))
        look = argv[argv.index('--look') + 1] if '--look' in argv else 'golden-sun'
        season = argv[argv.index('--season') + 1] if '--season' in argv else 'summer'
        g, k = grade(s, '--face' in argv, look, season)
        print(s, 'k=%.2f' % k); print(g)
    else:
        sys.exit(__doc__)
