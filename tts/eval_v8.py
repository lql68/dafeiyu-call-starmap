# -*- coding: utf-8 -*-
r"""v8 评估：先看 WORLD 造的参考还剩多少音色，再看 IndexTTS 输出。
   基准 B 修正为 c6400.wav。"""
import os, sys, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
import torch, torchaudio

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
TMP  = r"D:\deepseek harness\ai-live\tts\_tmp16k.wav"

CAND = [
    ("[基准]原歌A c2925",  REFD + r"\c2925.wav",           "base"),
    ("[基准]原歌B c6400",  REFD + r"\c6400.wav",           "base"),
    ("[基准]Huihui说",     REFD + r"\neutral_raw.wav",     "base"),
    ("——参考层——",         None,                            "sep"),
    ("vc_mean(参考)",      REFD + r"\vc_mean.wav",          "ref"),
    ("vc_mean_lofix(参考)", REFD + r"\vc_mean_lofix.wav",    "ref"),
    ("vc_half(参考)",      REFD + r"\vc_half.wav",          "ref"),
    ("her_timbre_breathed(参考)", REFD + r"\her_timbre_breathed.wav", "ref"),
    ("——输出层——",         None,                            "sep"),
    ("旧_未处理",           OUT + r"\clone_v2925.wav",       "gen"),
    ("v4_k40df085",        OUT + r"\v4_k40df085.wav",      "gen"),
    ("v7_her_加换气",       OUT + r"\v7_her_加换气.wav",     "gen"),
    ("v8_mean",            OUT + r"\v8_mean.wav",          "gen"),
    ("v8_mean_lofix",      OUT + r"\v8_mean_lofix.wav",    "gen"),
    ("v8_half",            OUT + r"\v8_half.wav",          "gen"),
]


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
    st = np.zeros_like(f0)
    if voiced.sum() > 2:
        st[voiced] = 12 * np.log2(f0[voiced] / np.median(f0[voiced]))
        idx = np.arange(len(st)); st = np.interp(idx, idx[voiced], st[voiced])
    d = np.abs(np.diff(st)); m = voiced[1:] & voiced[:-1]
    return dict(voiced=float(voiced.mean()), pauses=len(segs) / dur,
                longnote=ln / max(1, int(voiced.sum())),
                slope=float(np.median(d[m])) if m.sum() > 5 else 0.0, dur=dur,
                f0med=float(np.median(f0[voiced])) if voiced.any() else 0.0)


M = {}
for n, p, k in CAND:
    if p and os.path.exists(p):
        M[n] = sing_metrics(p)

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


E = {n: embed(p) for n, p, k in CAND if p and os.path.exists(p)}
A, B = E["[基准]原歌A c2925"], E["[基准]原歌B c6400"]
s_s, s_h = M["[基准]原歌A c2925"], M["[基准]Huihui说"]


def sing_idx(r):
    v = []
    for k in ("longnote", "pauses", "voiced"):
        a, b = s_h[k], s_s[k]
        if abs(b - a) < 1e-9: continue
        z = (b - r[k]) / (b - a) if k == "pauses" else (r[k] - a) / (b - a)
        v.append(max(0.0, min(1.6, z)))
    return float(np.mean(v))


print(f"{'版本':<24}{'音色A':>7}{'音色B':>7}{'均':>6}{'唱腔':>6}{'浊音':>6}{'停顿':>6}{'长音':>6}{'f0':>7}{'时长':>7}")
for n, p, kind in CAND:
    if not p:
        print(f"\n{n}")
        continue
    if n not in M or n not in E: continue
    a = float((A @ E[n].T).item()); b = float((B @ E[n].T).item())
    r = M[n]; si = sing_idx(r)
    print(f"{n:<24}{a:>7.3f}{b:>7.3f}{(a+b)/2:>6.3f}{si:>6.2f}{r['voiced']:>6.2f}"
          f"{r['pauses']:>6.2f}{r['longnote']:>6.2f}{r['f0med']:>7.0f}{r['dur']:>7.2f}")

print("\n综合分 = 音色均 × (1.35 - 唱腔)   [只算输出层]")
best = None
for n, p, kind in CAND:
    if kind != "gen" or n not in M or n not in E: continue
    a = float((A @ E[n].T).item()); b = float((B @ E[n].T).item())
    sc = (a + b) / 2 * (1.35 - sing_idx(M[n]))
    print(f"  {n:<22} {sc:.3f}")
    if best is None or sc > best[1]: best = (n, sc)
print(f"\n>>> 推荐: {best[0]}  ({best[1]:.3f})")