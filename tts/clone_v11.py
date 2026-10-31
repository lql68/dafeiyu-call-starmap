# -*- coding: utf-8 -*-
r"""v11：输出端后处理。音色用全通道她（0.83 音色），然后对合成结果做：
   1) 段内时间压缩 —— 只压单个连续浊音段的内部，不动跨音素的序列
   2) 段间插换气静音
   3) f0 平滑 + 起伏压缩
   再 WORLD 重合成。"""
import os, sys, subprocess, json, wave
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.ndimage import zoom
from scipy.signal import savgol_filter, medfilt

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
FP   = 5.0
SR   = 22050


def loadw(p, sr=SR):
    tmp = os.path.join(OUT, "_r11_src.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", p, "-ar", str(sr), "-ac", "1", tmp], check=True)
    return sf.read(tmp, dtype="float64")


def to24(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-ar", "24000", "-ac", "1",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    dst], check=True)
    return dst


def proc(y, sr, max_note=0.55, squeeze=0.62, gap_ms=70, f0k=0.55, smooth_ms=90):
    """max_note 秒以上的连续浊音段压到 max_note 秒；段间插入 gap_ms 静音。"""
    f0, t = pw.harvest(y, sr, f0_floor=70.0, f0_ceil=700.0, frame_period=FP)
    f0 = pw.stonemask(y, f0, t, sr)
    sp = pw.cheaptrick(y, f0, t, sr)
    ap = pw.d4c(y, f0, t, sr)

    voiced = f0 > 0
    fps = 1000.0 / FP
    maxf = int(max_note * fps)
    gapf = max(2, int(gap_ms / FP))

    # f0 平滑 + 压缩起伏（只处理浊音段内）
    if voiced.sum() > 12:
        win = max(5, int(smooth_ms / FP) | 1)
        lf = np.where(voiced, np.log(np.where(voiced, f0, 1.0)), 0.0)
        sm = savgol_filter(lf, win, 3)
        med = np.median(lf[voiced])
        lf2 = med + (sm - med) * f0k
        lf2 = medfilt(lf2, 7)
        f0 = np.where(voiced, np.exp(lf2), 0.0)

    # 切段
    segs, i, n = [], 0, len(voiced)
    while i < n:
        if voiced[i]:
            j = i
            while j < n and voiced[j]: j += 1
            segs.append((i, j)); i = j
        else:
            segs.append((i, i)); i += 1

    F0o, SPo, APo = [], [], []
    for a, b in segs:
        L = b - a
        if L == 0:
            # 未浊音段（辅音/静音）原样保留，一帧不能少
            F0o.append(np.zeros(1)); SPo.append(sp[a:a + 1]); APo.append(ap[a:a + 1])
            continue
        if L > maxf:
            T = maxf
            idx = np.round(np.linspace(0, L - 1, T)).astype(int)
            sps = sp[a:b][idx]; aps = ap[a:b][idx]
            m = f0[a:b].mean()
            f0s = np.repeat(m if m > 0 else 0.0, T)
        else:
            f0s, sps, aps = f0[a:b], sp[a:b], ap[a:b]
        F0o.append(f0s); SPo.append(sps); APo.append(aps)
        # 长音被压过之后补一小口换气
        if L > maxf and b < n and gap_ms > 0:
            F0o.append(np.zeros(gapf))
            SPo.append(np.tile(sp[a:b].min(axis=0), (gapf, 1)))
            APo.append(np.full((gapf, sp.shape[1]), 1.0))

    F0 = np.concatenate(F0o); SP = np.vstack(SPo); AP = np.vstack(APo)
    out = pw.synthesize(F0, np.ascontiguousarray(SP), np.ascontiguousarray(AP), sr,
                        frame_period=FP).astype(np.float32)
    return out / (np.abs(out).max() + 1e-9) * 0.85


# ---------- 用她的全通道结果做底 ----------
SRC = os.path.join(OUT, "v9_base_her.wav")
print(f"[src] {SRC}", flush=True)
y, sr = loadw(SRC)
print(f"     {len(y)/sr:.2f}s", flush=True)

rows = []
CFG = [
    ("a_轻", dict(max_note=0.65, squeeze=1.0, gap_ms=0,  f0k=0.80, smooth_ms=70)),
    ("b_中", dict(max_note=0.50, squeeze=1.0, gap_ms=55, f0k=0.60, smooth_ms=90)),
    ("c_重", dict(max_note=0.38, squeeze=1.0, gap_ms=80, f0k=0.45, smooth_ms=120)),
]
for tag, kw in CFG:
    o = proc(y, sr, **kw)
    raw = os.path.join(OUT, f"_r11_{tag}.wav")
    sf.write(raw, o, sr)
    dst = to24(raw, os.path.join(OUT, f"v11_{tag}.wav"))
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=tag, file=dst, dur=round(d, 2), cps=round(15 / d, 2), cfg=str(kw)))
    print(f"[gen] v11_{tag}  {d:.2f}s  {15/d:.2f}字/秒  {kw}", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))