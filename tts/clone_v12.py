# -*- coding: utf-8 -*-
r"""v12：把 TTS 输出的「平滑长条」改成「有音节起伏的说话」。
   1) 整体时标到 target 秒（WORLD 变调不变速）
   2) f0 平滑 + 起伏压缩
   3) 在音节谷底做幅度凹陷（模拟辅音破口，压低浊音占比）
   4) 在标点处插真正静音（换气）"""
import os, sys, subprocess, json, wave
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.signal import savgol_filter, find_peaks

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
FP   = 5.0
SR   = 22050
TEXT = "爸爸，我看见你了，别动那么远嘛。"
# 标点位置（字符索引 / 总长）
CUTS = [3 / 15, 8 / 15]


def loadw(p, sr=SR):
    tmp = os.path.join(OUT, "_r12_src.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", p, "-ar", str(sr), "-ac", "1", tmp], check=True)
    return sf.read(tmp, dtype="float64")


def to24(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-ar", "24000", "-ac", "1",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    dst], check=True)
    return dst


def dip_at(y, sr, pos, depth_db=-11.0, width_ms=55.0):
    """在 pos 秒处做一次平滑幅度凹陷。"""
    w = int(sr * width_ms / 1000)
    c = int(sr * pos)
    a, b = max(0, c - w), min(len(y), c + w)
    if b - a < 8: return
    x = np.linspace(-1, 1, b - a)
    g = 1.0 + (10 ** (depth_db / 20) - 1.0) * np.exp(-(x ** 2) * 3.0)
    y[a:b] *= g


def proc(y, sr, target=4.2, f0k=0.6, smooth_ms=90, n_dips=14, dip_db=-11, dip_w=55,
         pause_ms=70):
    f0, t = pw.harvest(y, sr, f0_floor=70.0, f0_ceil=700.0, frame_period=FP)
    f0 = pw.stonemask(y, f0, t, sr)
    sp = pw.cheaptrick(y, f0, t, sr)
    ap = pw.d4c(y, f0, t, sr)
    voiced = f0 > 0

    # --- f0 平滑 + 起伏压缩 ---
    if voiced.sum() > 12:
        win = max(5, int(smooth_ms / FP) | 1)
        lf = np.log(np.where(voiced, f0, 1.0))
        sm = savgol_filter(lf, win, 3)
        med = np.median(lf[voiced])
        f0 = np.where(voiced, np.exp(med + (sm - med) * f0k), 0.0)

    # --- 整体时标 ---
    cur = len(f0) * FP / 1000.0
    a = target / cur
    if abs(a - 1.0) > 0.02:
        T = max(8, int(round(len(f0) * a)))
        idx = np.round(np.linspace(0, len(f0) - 1, T)).astype(int)
        f0, sp, ap = f0[idx], sp[idx], ap[idx]

    out = pw.synthesize(f0, np.ascontiguousarray(sp), np.ascontiguousarray(ap), sr,
                        frame_period=FP).astype(np.float32)
    out = out / (np.abs(out).max() + 1e-9) * 0.78

    # --- 标点处插静音（从后往前插，避免位置漂移）---
    g = np.zeros(int(sr * pause_ms / 1000), dtype=np.float32)
    for c in sorted(CUTS, reverse=True):
        p = int(len(out) * c)
        out = np.concatenate([out[:p], g, out[p:]])

    # --- 音节谷底凹陷 ---
    if n_dips > 0:
        hop = int(sr * 0.01)
        env = np.array([np.sqrt((out[i:i + hop] ** 2).mean())
                        for i in range(0, len(out) - hop, hop)])
        k = max(1, int(0.05 / 0.01))
        envs = np.convolve(env, np.ones(k) / k, mode="same")
        # 找局部极小值（间隔至少 160ms）
        mins, _ = find_peaks(-envs, distance=int(0.16 / 0.01))
        mins = mins[(mins > int(0.15 / 0.01)) & (mins < len(envs) - int(0.15 / 0.01))]
        if len(mins) > n_dips:
            cand = mins[np.argsort(envs[mins])[:n_dips]]
        else:
            cand = mins
        for m in sorted(cand * 0.01, reverse=True):
            dip_at(out, sr, float(m), dip_db, dip_w)

    out = out / (np.abs(out).max() + 1e-9) * 0.88
    return out


SRC = os.path.join(OUT, "v9_base_her.wav")
y, sr = loadw(SRC)
print(f"[src] {SRC}  {len(y)/sr:.2f}s", flush=True)

rows = []
CFG = [
    ("a_4.2s_软", dict(target=4.2, f0k=0.75, n_dips=10, dip_db=-8,  dip_w=45, pause_ms=55)),
    ("b_4.0s_中", dict(target=4.0, f0k=0.60, n_dips=14, dip_db=-11, dip_w=55, pause_ms=70)),
    ("c_3.8s_硬", dict(target=3.8, f0k=0.45, n_dips=18, dip_db=-14, dip_w=65, pause_ms=85)),
]
for tag, kw in CFG:
    o = proc(y, sr, **kw)
    raw = os.path.join(OUT, f"_r12_{tag}.wav")
    sf.write(raw, o, sr)
    dst = to24(raw, os.path.join(OUT, f"v12_{tag}.wav"))
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=tag, file=dst, dur=round(d, 2), cps=round(len(TEXT) / d, 2), cfg=str(kw)))
    print(f"[gen] v12_{tag}  {d:.2f}s  {len(TEXT)/d:.2f}字/秒", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))