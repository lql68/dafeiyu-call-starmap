# -*- coding: utf-8 -*-
r"""去唱腔：WORLD 分解 → 保留谱包络(音色) → 重写 f0(去颤音+压缩音域) → 重合成。
音色 = sp(谱包络)，韵律 = f0 曲线。只改 f0，音色不动。"""
import os, sys, math, wave, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.signal import savgol_filter, medfilt

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
SEP  = r"D:\deepseek harness\ai-live\tts\sep\htdemucs\cover_full\vocals.wav"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
os.makedirs(REFD, exist_ok=True)

FP = 5.0   # frame_period ms → 200 fps


def load_16k(start, dur):
    tmp = os.path.join(REFD, "_tmp_cut.wav")
    subprocess.run([FF, "-y", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", SEP,
                    "-ar", "16000", "-ac", "1", tmp], check=True)
    x, sr = sf.read(tmp, dtype="float64")
    return x, sr


def semitones(f0, ref=None):
    v = f0[f0 > 0]
    if len(v) == 0: return (0, 0, 0)
    ref = ref if ref is not None else np.median(v)
    return (12 * math.log2(v.min() / ref), 12 * math.log2(v.max() / ref),
            12 * math.log2(np.percentile(v, 95) / np.percentile(v, 5)))


def devocalize(x, sr, tag, k=0.40, smooth_ms=180, pitch_shift_st=0.0, target_floor=None):
    f0, t = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=600.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)

    voiced = f0 > 0
    nv = int(voiced.sum())
    med = float(np.median(f0[voiced]))
    lo, hi, span = semitones(f0, med)
    print(f"[{tag}] voiced {nv}/{len(f0)} ({nv/len(f0)*100:.0f}%)  median={med:.1f}Hz  "
          f"音域 {lo:+.1f}~{hi:+.1f}半音 (p5-p95 跨度 {span:.1f} 半音)", flush=True)

    # --- 1. 去颤音：只对 voiced 段做 savgol 平滑（颤音 4-8Hz，180ms 窗足够压掉）
    win = int(round(smooth_ms / FP)) | 1
    f0s = f0.copy()
    idx = np.where(voiced)[0]
    if len(idx) > win:
        seg = f0s[idx]
        f0s[idx] = savgol_filter(seg, win, 2)
        # 平滑后再中值一次，掐掉 octave jump 残留
        f0s[idx] = medfilt(f0s[idx], kernel_size=9)
    # 平滑会抹平 voiced 边界，用原 voiced mask 复位非浊音
    f0s[~voiced] = 0.0

    # --- 2. 音域压缩：对数域向中位数收缩
    lf = np.log(np.maximum(f0s, 1e-6))
    med_l = float(np.median(lf[voiced]))
    lf_new = np.where(voiced, med_l + (lf - med_l) * k, lf)
    f0n = np.where(voiced, np.exp(lf_new), 0.0)
    if pitch_shift_st:
        f0n = np.where(voiced, f0n * (2 ** (pitch_shift_st / 12.0)), 0.0)

    lo2, hi2, span2 = semitones(f0n, med)
    print(f"[{tag}] 处理后 音域 {lo2:+.1f}~{hi2:+.1f}半音 跨度 {span2:.1f}  颤音已平滑({smooth_ms}ms)", flush=True)

    y = pw.synthesize(f0n, sp, ap, sr, frame_period=FP).astype(np.float32)
    y = y / (np.abs(y).max() + 1e-9) * 0.85
    dst = os.path.join(REFD, f"{tag}.wav")
    sf.write(dst, y, sr)
    print(f"[{tag}] -> {dst}  {len(y)/sr:.2f}s", flush=True)
    return dst, (lo, hi, span), (lo2, hi2, span2), med


def to24(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-ar", "24000", "-ac", "1",
                    "-af", "alimiter=limit=0.89:attack=3:release=40", dst], check=True)
    return dst


if __name__ == "__main__":
    jobs = [(29.25, 10.0, "spk2925"), (64.0, 10.0, "spk6400")]
    for start, dur, tag in jobs:
        x, sr = load_16k(start, dur)
        p, *_ = devocalize(x, sr, tag)
        to24(p, os.path.join(REFD, f"{tag}_24k.wav"))
    print("\n完成。参考文件：spk2925_24k.wav / spk6400_24k.wav")