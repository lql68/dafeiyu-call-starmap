# -*- coding: utf-8 -*-
r"""生成结果质检：峰值、包络、异常静音、削波。"""
import sys, wave, os, glob
sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np

FILES = [
    ("try_12   (带BGM 12s)",  r"D:\deepseek harness\ai-live\tts\try_12.wav"),
    ("try_64   (带BGM 64s)",  r"D:\deepseek harness\ai-live\tts\try_64.wav"),
    ("try_74   (带BGM 74s)",  r"D:\deepseek harness\ai-live\tts\try_74.wav"),
    ("v2925    (干净 29.25s)", r"D:\deepseek harness\ai-live\tts\out\cl_v2925.wav"),
    ("v6400    (干净 64s)",    r"D:\deepseek harness\ai-live\tts\out\cl_v6400.wav"),
]

def load(p):
    with wave.open(p) as w:
        sr = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
        a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)/32768.0
    if ch > 1: a = a.reshape(-1, ch).mean(axis=1)
    return a, sr

print(f"{'样本':<22}{'时长':>7}{'峰值':>7}{'RMS':>7}{'削波%':>7}{'静音段':>8}{'语速字/秒':>10}")
for name, p in FILES:
    if not os.path.exists(p):
        print(f"{name:<22}  缺失"); continue
    a, sr = load(p)
    dur = len(a)/sr
    peak = float(np.abs(a).max())
    rms = float(np.sqrt((a**2).mean()))
    clip = float((np.abs(a) > 0.995).mean()*100)
    # 100ms 窗找 < 0.005 的连续静音
    hop = int(0.1*sr); sil = 0; run = 0
    for i in range(len(a)//hop):
        if np.sqrt((a[i*hop:(i+1)*hop]**2).mean()) < 0.005:
            run += 1; sil = max(sil, run)
        else: run = 0
    # 有效发声时长（去掉首尾静音）
    nz = np.nonzero(np.abs(a) > 0.01)[0]
    eff = (nz[-1]-nz[0])/sr if len(nz) else 0
    print(f"{name:<22}{dur:>7.2f}{peak:>7.2f}{rms:>7.3f}{clip:>7.2f}{sil*0.1:>8.1f}{15/eff:>10.2f}")