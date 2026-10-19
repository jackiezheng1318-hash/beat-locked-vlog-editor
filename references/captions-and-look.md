# Captions, grade and face retouch

## Captions (optional — ask first)

- Default is **no captions**. Ask at intake: none / opening title only / title + place labels.
- Write a caption script and get approval before burning:

  | Time | Shot | Caption | Evidence |
  |---|---|---|---|
  | 0.00–3.76 | opening bus shot | Weekend city walk | title, no place claim |
  | 39.38–41.24 | park entrance stone | People's Park | name carved on the stone |

- **Place names need visual evidence**: zoom into the source frame and read the sign. Notes in a
  shot list, earlier edits or another tool's labels are not evidence (a real case: a department
  store was labelled as a famous hotel through three versions until someone read the sign).
- Labels: small (≈ 5.5 % of frame height), white with a thin black outline, centred low (82 %),
  0.1 s fades. Title: ≈ 10 %, centred, short pop-in, on the first 2 bars. Large heavy "card"
  captions tend to fight with scenic footage.
- Each caption enters and leaves on its shot's cut, so captions are on the beat too.
- Deliver both the captioned and the caption-free file.

## Scene-aware grade (`adaptive_grade.py`)

**1. Identify the scene** — light/weather, season (clip `creation_time`, foliage, clothing; southern
hemisphere flips), place type. Look at the contact sheets first; `adaptive_grade.py --suggest edl.json`
gives a hint from sky blue/grey share, vegetation, warmth, luma and contrast. It cannot separate
"indoors" from "outdoors under a market awning" (both warm, saturated, skyless), so you decide, and
for mixed footage set a per-shot `look` column.

**2. Pick a look** (`render_beat_locked.py --adaptive-grade`, auto by default, `--look` / `--season` to force):

| Look | Scene | What it does |
|---|---|---|
| golden-sun | sunny day | warm highlights, slightly cool shadows, gentle contrast (author-approved baseline) |
| overcast | grey sky | little warmth (warming grey sky looks dirty), more contrast + vibrance, neutral sky |
| golden-hour | low sun, already warm | barely add warmth, protect highlights |
| night | city night | no warming, deep blacks kept, teal-ish shadows, colour lifted |
| indoor | artificial light | neutralise the orange cast, mild contrast |
| snow | winter snow | clean cool whites, lifted exposure, restrained colour (auto only in winter) |

Season modifier on warmth: spring 0.8 (+ fresher greens), summer/autumn 1.0, winter 0.6.

**3. Per shot inside the look** — warmth factor = clip(1 − (R/B − 1.05) × 2, 0.35, 1) × clip(1 −
(luma − 115) / 150, 0.55, 1), × 0.45 on face shots; brighter shots get a softer highlight roll-off.
`looks.json` records each shot's look and factor, `scene-look.json` the scene decision and reasons.

New scene? Research colourist practice / open LUTs, read them before use, add a 16-bit-safe entry to
`LOOKS` (no `eq`), and show a before/after to the user the first time.

## Face retouch (`face_beauty.py`, macOS)

1. macOS Vision finds face box + landmarks every 4th frame on a 960-px copy; interpolated between.
2. Mask = feathered face ellipse × skin colour × NOT(eyes, brows, glasses, lips).
3. Edge-preserving guided filter (radius ≈ 4.5 % of face width), 15 % fine texture added back.
4. +3 % brightness and a slight yellow→neutral shift on skin only. Strength 0.85 by default.
5. Streams 16-bit frames at full resolution; encoded with the same 10-bit settings as other shots.

Use it on the main person only, never to reshape features. Show a before/after crop
(`--preview`) the first time and let the user set the strength.
