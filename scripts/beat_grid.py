#!/usr/bin/env python3
"""Measure a BGM's real beat grid: tempo, every beat, kick-aligned downbeats, bars, 8-bar phrases.

Numpy-only (no librosa). Why measure every beat: a grid extrapolated from one anchor + a
rounded BPM (e.g. 127.8 instead of 128.0, phase on beat 2 instead of 1) drifts 0.1-0.25 s off
the music within two minutes -- every cut "almost" lands, which viewers hear as off-beat.

Method: STFT spectral-flux onset envelope -> autocorrelation tempo -> Ellis dynamic-programming
beat tracker -> each beat refined to the local onset/kick peak (±25 ms) -> downbeat phase =
beat position (mod 4) with the strongest low-band (30-150 Hz) attack.

Usage: beat_grid.py <audio> <out.json>
Times are in seconds of the decoded audio file. Cut on `downbeats` (or `beats` for half-bar
accents); never extrapolate a constant grid from one anchor.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

import numpy as np

SR, HOP, NFFT = 22050, 128, 2048


def decode(path):
    ff = shutil.which('ffmpeg') or sys.exit('ffmpeg not found')
    raw = subprocess.run([ff, '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw, '<f4').astype(np.float32)


def onset(S, lo=None, hi=None):
    f = np.fft.rfftfreq(NFFT, 1 / SR); m = np.ones_like(f, bool)
    if lo: m &= f >= lo
    if hi: m &= f <= hi
    L = np.log1p(100 * S[:, m])
    e = np.maximum(0, np.diff(L, axis=0, prepend=L[:1])).sum(1)
    return np.maximum(e - np.convolve(e, np.ones(64) / 64, 'same'), 0)


def tempo(env, fps, lo=70, hi=180):
    x = env - env.mean(); ac = np.correlate(x, x, 'full')[len(x) - 1:]
    lags = np.arange(len(ac)); bpm = 60 * fps / np.maximum(lags, 1)
    m = (bpm >= lo) & (bpm <= hi)
    lag = lags[m][np.argmax(ac[m] * np.exp(-0.5 * (np.log2(bpm[m] / 120) / 0.9) ** 2))]
    a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
    return 60 * fps / (lag + 0.5 * (a - c) / (a - 2 * b + c))


def track(env, fps, bpm, tight=400):
    period = 60 * fps / bpm; n = len(env)
    score = env.copy(); back = -np.ones(n, int)
    offs = np.arange(int(round(-2 * period)), int(round(-period / 2)) + 1)
    pen = -tight * np.log(-offs / period) ** 2
    for t in range(n):
        idx = t + offs; ok = idx >= 0
        if ok.any():
            cand = score[idx[ok]] + pen[ok]; k = np.argmax(cand)
            score[t] = env[t] + cand[k]; back[t] = idx[ok][k]
    t = n - 1 - int(np.argmax(score[::-1][:int(period)])); out = []
    while t >= 0:
        out.append(t); t = back[t]
    return np.array(out[::-1])


def main(audio, out):
    x = decode(audio); fps = SR / HOP
    win = np.hanning(NFFT).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (NFFT // 2, NFFT // 2)), NFFT)[::HOP]
    S = np.abs(np.fft.rfft(frames * win, axis=1))
    env, kick = onset(S), onset(S, 30, 150)
    bpm = tempo(env, fps)
    comb = env / env.std() + kick / kick.std(); r = int(0.025 * fps)
    beats = []
    for b in track(env / (env.std() + 1e-9), fps, bpm):
        a = max(0, b - r); beats.append(a + int(np.argmax(comb[a:b + r + 1])))
    t = np.array(beats) / fps
    k = np.arange(len(t)); period, phase = np.linalg.lstsq(np.vstack([k, np.ones_like(k)]).T, t, rcond=None)[0]
    rms = np.sqrt(np.convolve(x ** 2, np.ones(2048) / 2048, 'same'))
    ks = np.array([kick[max(0, int(v * fps) - 3):int(v * fps) + 4].max() for v in t])
    phase_scores = [float(np.median(ks[p::4])) for p in range(4)]
    p0 = int(np.argmax(phase_scores))
    down = t[p0::4]
    bars = [dict(bar=i, t=round(float(s), 4), rms=round(float(rms[int(s * SR):int(e * SR)].mean()), 4))
            for i, (s, e) in enumerate(zip(down[:-1], down[1:]))]
    res = dict(audio=audio, method='numpy spectral-flux + Ellis DP beat tracker, kick-refined (beat_grid.py)',
               bpm=round(float(60 / period), 3), period=round(float(period), 6), first_beat=round(float(t[0]), 4),
               downbeat_phase=p0, downbeat_phase_kick_median=[round(v, 2) for v in phase_scores],
               residual_ms_median=round(float(np.median(abs(t - (k * period + phase)))) * 1000, 1),
               phrase_starts_8bar=[round(float(v), 4) for v in down[::8]],
               downbeats=[round(float(v), 4) for v in down], beats=[round(float(v), 4) for v in t], bars=bars,
               status='automatic measurement; section meaning still needs listening')
    json.dump(res, open(out, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ('bpm', 'first_beat', 'downbeat_phase', 'downbeat_phase_kick_median',
                                          'residual_ms_median')}, ensure_ascii=False))
    print('phrase starts:', res['phrase_starts_8bar'][:10])


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
