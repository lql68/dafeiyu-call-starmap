# -*- coding: utf-8 -*-
r"""通用评估：音色相似度(A=c2925, B=c6400 双基准) × 唱腔指数。"""
import os, sys, glob, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
import torch, torchaudio

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
TMP  = r"D:\deepseek harness\ai-live\tts\_tmp16k.wav"

PATTERN = sys.argv[1] if len(sys.argv) > 1 else "v9_*.wav"

base = [("[基础]原歌A", REFD + r"\c2925.wav"), ("[基础]原歌B", REFD + r"\c6400.wav"),
        ("[基础]Huihui说", REFD + r"\neutral_raw.wav")]
extra = [("v7_her_加换气", OUT + r"\v7_her_加换气.wav"), ("旧_未处理", OUT + r"\clone_v2925.wav")]
files = sorted(glob.glob(os.path.join(OUT, PATTERN)))
CAND = base + [(os.path.basename(f)[:-4], f) for f in files] + extra
CAND = [(n, p) for n, p in CAND if os.path.exists(p)]


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
    env = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, len(x) - hop, hop)])
    thr = max(0.01, np.percentile(env, 20) * 0.4)
    segs, run = [], 0
    for s in (env < thr):
        if s: run += 1
        else:
            if run >= 6: segs.append(run)
            run = 0
    if run >= 6: segs.append(run)
    dur = len(x) / sr
    ln, cur = 0, 0
    for v in voiced:
        if v: cur += 1
        else:
            if cur >= int(0.8 * fps): ln += cur
            cur = 0
    if cur >= int(0.8 * fps): ln += cur
    return dict(voiced=float(voiced.mean()), pauses=len(segs) / dur,
                longnote=ln / max(1, int(voiced.sum())), dur=dur,
                f0med=float(np.median(f0[voiced])) if voiced.any() else 0.0)


M = {n: sing_metrics(p) for n, p in CAND}

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


E = {n: embed(p) for n, p in CAND}
A, B = E["[基础]原歌A"], E["[基础]原歌B"]
s_s, s_h = M["[基础]原歌A"], M["[基础]Huihui说"]


def sing_idx(r):
    """z=0 表示纯说话(Huihui)，z=1 表示纯歌唱(原歌)。三项同向，不做额外反转。"""
    v = []
    for k in ("longnote", "pauses", "voiced"):
        a, b = s_h[k], s_s[k]
        if abs(b - a) < 1e-9: continue
        v.append(max(0.0, min(1.6, (r[k] - a) / (b - a))))
    return float(np.mean(v))


print(f"{'版本':<30}{'音色A':>7}{'音色B':>7}{'均':>6}{'唱腔':>6}{'浊音':>6}{'停顿':>6}{'长音':>6}{'f0':>7}{'时长':>7}")
best = None
for n, p in CAND:
    a = float((A @ E[n].T).item()); b = float((B @ E[n].T).item())
    r = M[n]; si = sing_idx(r)
    print(f"{n:<30}{a:>7.3f}{b:>7.3f}{(a+b)/2:>6.3f}{si:>6.2f}{r['voiced']:>6.2f}"
          f"{r['pauses']:>6.2f}{r['longnote']:>6.2f}{r['f0med']:>7.0f}{r['dur']:>7.2f}")
    if not n.startswith("[基础]"):
        sc = (a + b) / 2 * (1.35 - si)
        if best is None or sc > best[1]: best = (n, sc, (a + b) / 2, si)

print(f"\n>>> 最优: {best[0]}  综合 {best[1]:.3f}  音色 {best[2]:.3f}  唱腔 {best[3]:.2f}")
print(f"    （音色天花板 = 原歌A vs 原歌B = {float((A@B.T).item()):.3f}）")