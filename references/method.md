# The method: music decides the sections, content decides the shots

Distilled from a real city-walk edit that the author approved ("the cutting and the beat sync are
very good") after an earlier, grid-extrapolated cut scored ~75/100 with 0 of 27 cuts on the beat
and almost every shot the same 3.75 s length. One approved example is not a law: use this as the
default and adapt it to the footage.

## 1. Read the song first

- Measure every beat and the kick-drum bar starts (`beat_grid.py`). At ~128 BPM, 1 bar ≈ 1.875 s
  and an 8-bar phrase ≈ 15 s.
- Label sections from bar energy: intro, vocal entry / verse, chorus / peak, breakdown / drop,
  build-up, outro.
- One place or idea per phrase. Change location at phrase boundaries.

## 2. Shot length follows section energy

| Section | Shot length | Use it for |
|---|---|---|
| Intro | 1 bar × 3–4 (preview) → 2 bars | Promise "where we go today", then introduce the person and setting |
| Vocal entry / verse | alternate 2 bars and 1 bar | Look around: streets, shops, details |
| Last bar before a new section | two half-bars | Push the viewer into the next section |
| Chorus / peak | 1 bar every shot | The most distinctive, densest material |
| Breakdown / drop | 2 bars | Slow down: selfie, look-back, a breath |
| Build-up after the drop | 4 × half-bar | Sprint to the big downbeat |
| Ending | land on a phrase downbeat, ~2 bars | Music and picture fade together |

Every cut sits on the frame at or just before the kick (0–20 ms early reads as "tight").

## 3. Structure: preview → set out → look around → local highlight → end at the climax

1. **Preview (≈ 4 bars).** The most representative images of the day. **The very first shot must be
   steady and striking** — a big moving landmark (e.g. a double-decker bus crossing a landmark
   building) can take 2 bars so the motion completes. Shaky or messy shots never open the video,
   however interesting their content.
2. **The person appears** — one selfie/walking shot says "I'm here". At most one selfie per section.
3. **Follow the real route.** Ordinary streets first, getting busier; best place last.
4. **Give local specialities a full phrase** (≈ 8 shots on a chorus) instead of one passing shot.
5. **The climax location owns the second half** and the video **ends there**. Drop everything
   filmed after leaving it — no "walking away" filler for atmosphere.

## 4. Shot selection

- Give each shot a search window, let the script choose the steadiest stretch.
- Landmarks: only the 1–2 s where the sign/building is complete in frame; cut when the camera moves on.
- Review first/middle/last frames of every shot (`shot_review.py`) — handheld POV windows hide
  fingers, arms, phones and whip-pans at their edges.
- Delete "repeated sentences": the same kind of street/shop/sign only stays if it adds something new.

## 5. Picture and sound

- Scene-aware grade (`--adaptive-grade`): pick the look from the footage (sunny / overcast / golden hour /
  night / indoor / snow × season), then per shot: bright and already-warm shots and faces get less warmth.
  One warm look everywhere turns grey skies muddy and indoor light orange.
- Face retouch (`beauty=1`) on the main person only: blemishes off, features sharp, no reshaping.
- BGM from 0 s, no fade-in when the song opens on a kick; fade out from the last phrase start.
- Street ambience low (≈ −20 dB) under the music; mute selfie chatter that was not reviewed.

## 6. Export spec (hard rule)

- Output = source resolution, frame rate and bit depth (e.g. 3840×2160, 50 fps, 10-bit HEVC Main10,
  CRF 16 — usually at or above the camera bitrate).
- Encode once; grade in 16-bit RGB; no 8-bit-only filters. (Measured: an `eq` filter in the chain
  collapsed a 10-bit gradient to 207 levels; the 16-bit chain kept 778.)
- Check with ffprobe before delivering and write the spec into the edit note.
