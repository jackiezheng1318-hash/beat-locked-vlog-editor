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

## Adaptive warm grade (`adaptive_grade.py`)

Per shot, three frames are measured (mean luma, R/B warmth ratio, share of near-white pixels):

- warmth factor = clip(1 − (R/B − 1.05) × 2, 0.35, 1)  — already-warm shots get less
- brightness factor = clip(1 − (luma − 115) / 150, 0.55, 1) — bright sun gets less
- × 0.45 on face shots; softer highlight roll-off when bright

Chain (16-bit planar RGB): colour temperature 5400 K mix → master curve with gentle contrast →
colour balance (cool shadows, warm highlights) → vibrance → Rec.709 saturation matrix.
For a neutral look omit `--adaptive-grade`; for your own look use `--grade-file` (16-bit-safe filters only).

## Face retouch (`face_beauty.py`, macOS)

1. macOS Vision finds face box + landmarks every 4th frame on a 960-px copy; interpolated between.
2. Mask = feathered face ellipse × skin colour × NOT(eyes, brows, glasses, lips).
3. Edge-preserving guided filter (radius ≈ 4.5 % of face width), 15 % fine texture added back.
4. +3 % brightness and a slight yellow→neutral shift on skin only. Strength 0.85 by default.
5. Streams 16-bit frames at full resolution; encoded with the same 10-bit settings as other shots.

Use it on the main person only, never to reshape features. Show a before/after crop
(`--preview`) the first time and let the user set the strength.
