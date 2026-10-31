# -*- coding: utf-8 -*-
r"""v13：纯波形域处理，不碰 WORLD（保留音色），只改节奏。
   atempo 变速（保音高、保谱包络）+ 标点处插静音 + 音节谷底幅度凹陷。"""
import os, sys, subprocess, json, wave
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
from scipy.signal import find_peaks

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
TEXT = "爸爸，我看见你了，别动那么远嘛。"
CUTS = [3 / 15, 8 / 15]
SR   = 24000


def atempo(src, dst, factor):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af", f"atempo={factor:.4f}",
                    "-ar", str(SR), "-ac", "1", dst], check=True)
    return dst


def dip(y, sr, pos, depth_db, width_ms):
    w = int(sr * width_ms / 1000)
    c = int(sr * pos)
    a, b = max(0, c - w), min(len(y), c + w)
    if b - a < 8: return
    x = np.linspace(-1, 1, b - a)
    g = 1.0 + (10 ** (depth_db / 20) - 1.0) * np.exp(-(x ** 2) * 3.0)
    y[a:b] *= g


def build(src, target, n_dips, dip_db, dip_w, pause_ms, tag):
    with wave.open(src) as w:
        dur = w.getnframes() / w.getframerate()
    fac = dur / target
    tmp = os.path.join(OUT, f"_r13_{tag}_t.wav")
    atempo(src, tmp, fac)
    y, sr = sf.read(tmp, dtype="float64")
    y = y / (np.abs(y).max() + 1e-9) * 0.80

    g = np.zeros(int(sr * pause_ms / 1000))
    for c in sorted(CUTS, reverse=True):
        p = int(len(y) * c)
        y = np.concatenate([y[:p], g, y[p:]])

    hop = int(sr * 0.01)
    env = np.array([np.sqrt((y[i:i + hop] ** 2).mean()) for i in range(0, len(y) - hop, hop)])
    k = max(1, int(0.05 / 0.01))
    envs = np.convolve(env, np.ones(k) / k, mode="same")
    mins, _ = find_peaks(-envs, distance=int(0.16 / 0.01))
    mins = mins[(mins > 15) & (mins < len(envs) - 15)]
    cand = mins[np.argsort(envs[mins])[:n_dips]] if len(mins) > n_dips else mins
    for m in sorted(cand * 0.01, reverse=True):
        dip(y, sr, float(m), dip_db, dip_w)

    y = y / (np.abs(y).max() + 1e-9) * 0.89
    raw = os.path.join(OUT, f"_r13_{tag}.wav")
    sf.write(raw, y, sr)
    dst = os.path.join(OUT, f"v13_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", raw, "-ar", "24000", "-ac", "1",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    dst], check=True)
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    print(f"[gen] v13_{tag}  {d:.2f}s  {len(TEXT)/d:.2f}字/秒", flush=True)
    return dict(name=tag, file=dst, dur=round(d, 2), cps=round(len(TEXT) / d, 2))


SRC = os.path.join(OUT, "v9_base_her.wav")
rows = []
rows.append(build(SRC, 4.3, 8,  -6,  40, 45, "a_轻"))
rows.append(build(SRC, 4.1, 13, -10, 55, 65, "b_中"))
rows.append(build(SRC, 3.9, 17, -13, 62, 80, "c_硬"))
rows.append(build(SRC, 4.1, 1, -10, 55, 65, "e_变速换气无凹陷"))
print("\n" + json.dumps([r for r in rows if r], ensure_ascii=False, indent=1))