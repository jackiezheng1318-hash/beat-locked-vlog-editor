---
name: beat-locked-vlog-editor
description: Cut a music-driven vlog montage from raw footage with every cut locked to the measured kick drum of the BGM — city walks, travel, food/shop visits, events, daily-life montages, especially handheld/POV footage. Measures the song's real beat grid, picks the steadiest in-points, renders frame-exact at the source resolution/fps/bit depth (e.g. 4K50 10-bit), and verifies sync on the finished file. Optional per-shot warm grade, face retouch (macOS) and captions. Use when the user gives a folder of clips plus a song and wants an edited video; not for talking-head / interview / dialogue-driven edits.
---

# Beat-locked vlog editor

Turn a folder of raw clips + one BGM track into a finished montage where **every cut lands on the
kick drum**, the shot rhythm follows the song's structure, and the export is **never below the
source spec**.

The user is the author. You do inventory, selection proposals, rhythm, rendering and QA; the user
decides what the video is about and judges the result. Show work early, take feedback by timecode.

## Fits / doesn't fit

- Fits: music-driven montages with little or no dialogue — city walk, travel day, food or shop
  visits, exhibitions/events, weekend or daily-life vlogs; handheld, gimbal, action-cam or phone
  footage; 30 s – 5 min; landscape or vertical.
- Doesn't fit: talking-head, interviews, tutorials, anything cut on speech; scripted narrative
  that needs continuity editing; videos without a BGM (the method is built around the beat grid).

## Requirements

`ffmpeg`/`ffprobe` ≥ 6 with libx265 and the filters `colortemperature`, `vibrance`, `scdet`;
Python ≥ 3.9 with `numpy` and `Pillow`. Face retouch additionally needs macOS + Swift
(`scripts/detect_faces.swift`). See README.md for install steps and a self-test.

## 1. Intake — ask before cutting

Ask with the question tool, one round, only what is missing:

1. **Captions?** — none (default) / opening title only / opening title + place labels.
   Always ask this first; never decide it for the user.
2. **What should viewers remember?** One sentence (e.g. "a relaxed autumn Saturday downtown").
3. Raw folder, BGM file, target length (approximate). Aspect, resolution and frame rate follow the
   source (vertical stays vertical, 1080 stays 1080, 4K stays 4K, 59.94 stays 59.94) — don't ask.
4. Must-keep / must-drop shots, people to retouch (the main person only), places to feature.

## 2. Measure the music

```
python scripts/beat_grid.py <bgm> work/beats.json
```

- Uses every measured beat and the kick-drum downbeat. **Never extrapolate a grid from one
  anchor + BPM** — a 0.2-BPM rounding or a wrong bar phase puts cuts 0.1–0.25 s off by minute two.
- From `bars[].rms` mark the sections: intro, verse/vocal entry, chorus/peak, drop/breakdown,
  build-up, outro. 8-bar phrases (`phrase_starts_8bar`) are the natural section boundaries.

## 3. Inventory the footage

```
python scripts/shot_stability.py work/stability.json <clips...>
python scripts/raw_contact_sheets.py work/sheets work/stability.json <clips...>
```

Read every sheet. Note candidate windows (`clip, from–to s, what it shows`). Green = steady,
red = shaky. Landmarks/signs: note the exact seconds where the sign is fully readable.

## 4. Plan the structure on the music

Follow [references/method.md](references/method.md): one place or idea per 8-bar phrase, shot
length driven by the section energy, a strong preview opening, the best location saved for the
end, cut away from the climax location only if the user asks.

Write `work/shots.csv`:

```
path,search_in,search_out,bars,note,ambience,beauty
clips/C0012.MP4,180,186.5,2,opening: double-decker bus crosses frame,,0
clips/C0003.MP4,10,20,2,me walking into the sun,0,1
...
clips/C0031.MP4,18,31,END,last shot on the climax street,,0
```

- `bars`: 0.5 / 1 / 2 / 4 … (1 bar = 4 beats); last row `END`. The running sum decides where
  each cut falls, so plan sections by summing bars.
- `search_in/out`: a window, not an in-point — the script picks the steadiest stretch inside.
- `ambience`: raw-audio gain (blank = default 0.1 ≈ −20 dB; `0` mutes selfie talk).
- `beauty`: `1` on shots where the main person's face is large in frame.

```
python scripts/beat_locked_edl.py work/shots.csv work/beats.json work/stability.json work/edl --end <seconds>
```

`--end` = the downbeat where the video should finish (usually a phrase start + ~2 bars).

## 5. Review every shot before rendering

```
python scripts/shot_review.py work/edl.json work/review
```

Look at first / middle / last frame of every shot. Fix fingers, arms, phones, whip-pans, cut-off
signs, blur, ugly framing by narrowing that row's window and re-running step 4. The first shot
must be steady and striking. Only caption a place name you can read on a sign in the frame.

## 6. Render at source spec

```
python scripts/render_beat_locked.py work/edl.json <bgm> out/final.mp4 work/render \
    --adaptive-grade [--detector bin/detect_faces] --music-fade-from <last phrase start> --video-fade 1.5
```

- Output = source resolution, frame rate and 10-bit HEVC (CRF 16). The script refuses to
  downscale unless `--allow-downscale` (only on explicit request, as a separate file).
- Graded once in 16-bit RGB, encoded once; fade baked into the last shot; final mux is a copy.
- `--adaptive-grade` = scene-aware grade. First identify the scene yourself from the contact sheets
  (light/weather × season × place) and check it against `python scripts/adaptive_grade.py --suggest
  work/edl.json`; the renderer picks a look for the whole video (golden-sun, overcast, golden-hour,
  night, indoor, snow, with a season modifier from the clip date) and then scales warmth per shot
  (less on bright/warm shots and faces). Override with `--look` / `--season` (`--south` for the
  southern hemisphere); for mixed indoor/outdoor footage set a per-shot `look` column in shots.csv.
  The stats cannot tell indoors from "outdoors under an awning" — your visual judgement decides.
  For a scene no look covers (beach, neon night, snowy peaks…), research colourist references / open
  LUTs, add a 16-bit-safe look to `LOOKS`, and show the user a before/after first.
  Omit for no grade, or `--grade-file` for your own 16-bit-safe filter chain (no `eq`).
- BGM starts at 0 s with no fade-in when the song opens on a kick. Use `--music-offset` if a cold
  open plays before the music.
- 4K renders run ~10–15× slower than real time: run in the background.

## 7. Verify and deliver

```
python scripts/verify_beat_sync.py out/final.mp4 work/beats.json <bgm>
ffprobe -v error -show_entries stream=width,height,r_frame_rate,pix_fmt,profile out/final.mp4
```

- **Gate: ≥ 90 % of detected cuts within ±40 ms of a beat.** EDL numbers are not proof; this
  measures cuts from the pixels and the music position from the mix.
- Spec must match the source. Check loudness (`ebur128`, aim ≈ −14 LUFS) and black/freeze frames.
- Deliver: the video, the EDL, a short edit note (structure table, spec, sync result), and the
  open questions for the user. Say plainly what you could not check (you cannot watch in real
  time; rhythm and taste are the user's call).

## Optional: captions

Only if the user chose captions at intake. Draft the caption script first (time | shot | text |
evidence it is correct) and get approval, then:

```
python scripts/burn_captions.py out/final.mp4 captions.json out/final-captions.mp4 [--font file]
```

Keep the caption-free file too. Re-run `verify_beat_sync.py` on the captioned file.

## Hard rules

- Never modify, move or delete the raw footage. Write everything to new files.
- Never export below the source resolution, frame rate or bit depth unless the user explicitly asks.
- No 8-bit-only filters (e.g. `eq`) in the grade; encode the picture once.
- Never caption a place name without visual evidence in the frame.
- Delete intermediate versions only after the user confirms, and prefer moving them to the trash.
