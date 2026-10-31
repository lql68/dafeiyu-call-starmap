# -*- coding: utf-8 -*-
r"""统一评估：音色相似度(像不像她) × 唱腔指数(像不像说话)，选最优版本。"""
import os, sys, math, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.signal import medfilt
import torch, torchaudio

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
TMP  = r"D:\deepseek harness\ai-live\tts\_tmp16k.wav"

CAND = [
    ("旧_未处理",          OUT + r"\clone_v2925.wav",      "gen"),
    ("v4_k40df085",       OUT + r"\v4_k40df085.wav",     "gen"),
    ("v6_seg12_sil300",   OUT + r"\v6_seg12_sil300.wav", "gen"),
    ("v7_mix_中性节奏",    OUT + r"\v7_mix_中性节奏.wav",   "gen"),
    ("v7_her_加换气",      OUT + r"\v7_her_加换气.wav",     "gen"),
    ("[基准]原歌(唱)",      REFD + r"\c2925.wav",          "base"),
    ("[基准]Huihui(说)",   REFD + r"\neutral_raw.wav",    "base"),
]

# ---------- 唱腔指标 ----------
def load16(p):
    subprocess.run([FF, "-y", "-v", "error", "-i", p, "-ar", "16000", "-ac", "1", TMP], check=True)
    return sf.read(TMP, dtype="float64")

def sing_metrics(p):
    x, sr = load16(p)
    FP = 10.0
    f0, t = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=700.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, t, sr)
    voiced = f0 > 0
    fps = 1000.0 / FP
    hop = int(0.01 * sr)
    env = np.array([np.sqrt((x[i:i+hop]**2).mean()) for i in range(0, len(x)-hop, hop)])
    thr = max(0.01, np.percentile(env, 20) * 0.4)
    silent = env < thr
    segs, run = [], 0
    for s in silent:
        if s: run += 1
        else:
            if run >= 6: segs.append(run)
            run = 0
    if run >= 6: segs.append(run)
    dur = len(x)/sr
    ln, cur = 0, 0
    for v in voiced:
        if v: cur += 1
        else:
            if cur >= int(0.8*fps): ln += cur
            cur = 0
    if cur >= int(0.8*fps): ln += cur
    st = np.zeros_like(f0)
    if voiced.sum() > 2:
        st[voiced] = 12*np.log2(f0[voiced]/np.median(f0[voiced]))
        idx = np.arange(len(st)); st = np.interp(idx, idx[voiced], st[voiced])
    d = np.abs(np.diff(st)); m = voiced[1:] & voiced[:-1]
    return dict(voiced=float(voiced.mean()), pauses=len(segs)/dur,
                longnote=ln/max(1, int(voiced.sum())),
                slope=float(np.median(d[m])) if m.sum() > 5 else 0.0, dur=dur)

M = {n: sing_metrics(p) for n, p, _ in CAND if os.path.exists(p)}

# ---------- 音色相似度 ----------
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus
spk = CAMPPlus(feat_dim=80, embedding_size=192).eval()
spk.load_state_dict(torch.load(r"D:\index-tts\checkpoints\hf_cache\campplus_cn_common.bin",
                               map_location="cpu", weights_only=False))

def embed(p):
    w, s = torchaudio.load(p); w = w.mean(0, keepdim=True)
    if s != 16000: w = torchaudio.functional.resample(w, s, 16000)
    f = torchaudio.compliance.kaldi.fbank(w, num_mel_bins=80, sample_frequency=16000, dither=0.0)
    f = f - f.mean(dim=0, keepdim=True)
    with torch.no_grad(): e = spk(f.unsqueeze(0))
    return torch.nn.functional.normalize(e, dim=-1)

E = {n: embed(p) for n, p, _ in CAND if os.path.exists(p)}
A, B = E["[基准]原歌(唱)"], E["[基准]Huihui(说)"]

# 唱腔指纹：用 slope(滑音连续性) + longnote + pauses 三项，基准归一
s_s, s_h = M["[基准]原歌(唱)"], M["[基准]Huihui(说)"]
def sing_idx(r):
    v = []
    for k, inv in [("longnote", False), ("pauses", True), ("voiced", False)]:
        a, b = s_h[k], s_s[k]
        if abs(b - a) < 1e-9: continue
        z = (r[k]-a)/(b-a)
        if inv: z = (a-r[k])/(a-b)
        v.append(max(0.0, min(1.6, z)))
    return float(np.mean(v))

print(f"{'版本':<20}{'音色-歌A':>9}{'音色-歌B':>9}{'均':>7}{'唱腔':>7}{'浊音':>7}{'停顿/s':>8}{'长音':>7}{'时长':>7}")
for n, p, kind in CAND:
    if n not in M or n not in E: continue
    a = float((A @ E[n].T).item()); b = float((B @ E[n].T).item())
    r = M[n]; si = sing_idx(r)
    tag = "  ← 基准" if kind == "base" else ""
    print(f"{n:<20}{a:>9.3f}{b:>9.3f}{(a+b)/2:>7.3f}{si:>7.2f}{r['voiced']:>7.2f}"
          f"{r['pauses']:>8.2f}{r['longnote']:>7.2f}{r['dur']:>7.2f}{tag}")

print("\n综合分 = 音色均 × (1.4 - 唱腔)  (音色越高越好，唱腔越低越好)")
best = None
for n in M:
    if n not in E or n.startswith("["): continue
    a = float((A @ E[n].T).item()); b = float((B @ E[n].T).item())
    score = (a+b)/2 * (1.4 - sing_idx(M[n]))
    print(f"  {n:<20} {score:.3f}")
    if best is None or score > best[1]: best = (n, score)
print(f"\n>>> 推荐: {best[0]}  ({best[1]:.3f})")