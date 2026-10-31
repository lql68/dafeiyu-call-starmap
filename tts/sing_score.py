# -*- coding: utf-8 -*-
r"""量化「唱腔程度」：用 f0 轨迹与停顿结构给每个音频打分，基准是原歌(唱)与 Huihui(说)。
指标：
  vibrato   4-8Hz 颤音能量（半音 RMS）——唱歌最标志性的特征
  slope     f0 相邻帧变化中位值（半音）——说话有跳进，唱歌是连续滑音
  voiced    浊音占比——唱歌接近 100%，说话 60-75%
  pause     每秒停顿数——说话有换气，唱歌几乎不断
  longnote  >=0.8s 连续浊音占比——拖长音
"""
import os, sys, math, json, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.signal import butter, filtfilt, medfilt

FF = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
TMP  = r"D:\deepseek harness\ai-live\tts\_tmp16k.wav"

FILES = [
    ("原歌人声(唱)",       REFD + r"\c2925.wav",        "sing"),
    ("Huihui(纯说话)",     REFD + r"\neutral_raw.wav",  "speak"),
    ("WORLD处理后的参考",  REFD + r"\dv_k40df085.wav",  "ref"),
    ("旧_未处理克隆",      OUT + r"\clone_v2925.wav",   "gen"),
    ("v4_k40df085",       OUT + r"\v4_k40df085.wav",   "gen"),
    ("v4_k60df100",       OUT + r"\v4_k60df100.wav",   "gen"),
    ("v5_B_解耦",         OUT + r"\v5_B_解耦.wav",      "gen"),
    ("v5_A_纯Huihui",     OUT + r"\v5_A_纯Huihui.wav",  "gen"),
]


def load16(p):
    subprocess.run([FF, "-y", "-v", "error", "-i", p, "-ar", "16000", "-ac", "1", TMP], check=True)
    x, sr = sf.read(TMP, dtype="float64")
    return x, sr


def analyze(p):
    x, sr = load16(p)
    FP = 10.0
    f0, t = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=700.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, t, sr)
    voiced = f0 > 0
    vr = float(voiced.mean())

    # --- f0 转半音（仅浊音，线性插值填满）
    st = np.zeros_like(f0)
    if voiced.sum() > 2:
        st[voiced] = 12 * np.log2(f0[voiced] / np.median(f0[voiced]))
        idx = np.arange(len(st))
        st = np.interp(idx, idx[voiced], st[voiced])

    fps = 1000.0 / FP
    # --- 颤音：去趋势后 4-8Hz 带通
    med = medfilt(st, kernel_size=int(0.5 * fps) | 1)
    det = st - med
    b, a = butter(3, [4.0 / (fps / 2), 8.0 / (fps / 2)], btype="band")
    vib = filtfilt(b, a, det)
    vibrato = float(np.sqrt((vib ** 2).mean()))

    # --- f0 变化速率（只看浊音相邻段）
    d = np.abs(np.diff(st))
    mask = voiced[1:] & voiced[:-1]
    slope = float(np.median(d[mask])) if mask.sum() > 5 else 0.0

    # --- 停顿：10ms 能量包络低于阈值
    hop = int(0.01 * sr)
    env = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, len(x) - hop, hop)])
    thr = max(0.01, np.percentile(env, 20) * 0.4)
    silent = env < thr
    # 统计 >=60ms 的静音段
    segs, run = [], 0
    for s in silent:
        if s: run += 1
        else:
            if run >= 6: segs.append(run)
            run = 0
    if run >= 6: segs.append(run)
    dur = len(x) / sr
    pauses = len(segs) / dur

    # --- 长音：连续浊音 >=0.8s 的帧占浊音帧比例
    ln, cur = 0, 0
    for v in voiced:
        if v: cur += 1
        else:
            if cur >= int(0.8 * fps): ln += cur
            cur = 0
    if cur >= int(0.8 * fps): ln += cur
    longnote = ln / max(1, int(voiced.sum()))

    return dict(vibrato=vibrato, slope=slope, voiced=vr, pauses=pauses,
                longnote=longnote, dur=dur)


rows = {}
for name, p, kind in FILES:
    if not os.path.exists(p):
        print("缺失:", p); continue
    rows[name] = analyze(p)
    r = rows[name]
    print(f"{name:<20} vib={r['vibrato']:.3f}  slope={r['slope']:.3f}  "
          f"voiced={r['voiced']:.2f}  pause={r['pauses']:.2f}/s  long={r['longnote']:.2f}  "
          f"dur={r['dur']:.2f}s", flush=True)

# --- 归一化到 0..1（0=纯说话，1=原唱），五项等权
if "原歌人声(唱)" in rows and "Huihui(纯说话)" in rows:
    sing, spk = rows["原歌人声(唱)"], rows["Huihui(纯说话)"]
    print("\n=== 唱腔指数（0=像说话  1=像唱歌）===", flush=True)
    for name, r in rows.items():
        sc = []
        for k, w in [("vibrato", 1), ("slope", 1), ("voiced", 1), ("pauses", -1), ("longnote", 1)]:
            a, b = spk[k], sing[k]
            if abs(b - a) < 1e-9: continue
            v = (r[k] - a) / (b - a)
            if w < 0: v = (a - r[k]) / (a - b) if abs(a - b) > 1e-9 else 0
            sc.append(max(0.0, min(1.5, v)))
        print(f"  {name:<20} {np.mean(sc):.2f}")