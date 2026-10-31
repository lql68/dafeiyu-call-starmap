# -*- coding: utf-8 -*-
r"""v3：用「去唱腔后的参考」克隆，并对比 duration_factor 对语速的作用。"""
import os, sys, json, time, math, wave, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import torch, torchaudio

INDEX = r"D:\index-tts"
FF    = r"C:\Users\liu\bin\ffmpeg.exe"
REFD  = r"D:\deepseek harness\ai-live\tts\refs"
OUT   = r"D:\deepseek harness\ai-live\tts\out"
os.makedirs(OUT, exist_ok=True)

TEXT = "爸爸，我看见你了，别动那么远嘛。"

REFS = [
    ("spk2925", os.path.join(REFD, "spk2925_24k.wav"), 1.00),
    ("spk2925", os.path.join(REFD, "spk2925_24k.wav"), 0.85),
    ("spk6400", os.path.join(REFD, "spk6400_24k.wav"), 1.00),
]

def dur_of(p):
    with wave.open(p) as w: return w.getnframes() / w.getframerate()

def norm(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    return dst

from indextts.infer_v2_5 import IndexTTS2

t0 = time.time()
tts = IndexTTS2(cfg_path=os.path.join(INDEX, "checkpoints", "config.yaml"),
                model_dir=os.path.join(INDEX, "checkpoints"),
                use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

rows = []
for tag, ref, df in REFS:
    name = f"{tag}_df{str(df).replace('.','')}"
    raw = os.path.join(OUT, f"_raw3_{name}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=ref, text=TEXT, output_path=raw, lang="zh",
              stream_return=False, duration_factor=df)
    cost = time.time() - ts
    dst = norm(raw, os.path.join(OUT, f"clean_{name}.wav"))
    d = dur_of(dst)
    rows.append(dict(name=name, file=dst, cost=round(cost, 2), dur=round(d, 2),
                     cps=round(len(TEXT) / d, 2)))
    print(f"[gen] {name}  cost={cost:.2f}s  dur={d:.2f}s  语速={len(TEXT)/d:.2f}字/秒", flush=True)

torch.cuda.empty_cache()

# ---- 相似度：以原始歌人声为音色基准 ----
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus
spk = CAMPPlus(feat_dim=80, embedding_size=192).eval()
spk.load_state_dict(torch.load(os.path.join(INDEX, "checkpoints", "hf_cache", "campplus_cn_common.bin"),
                               map_location="cpu", weights_only=False))

def embed(p):
    w, sr = torchaudio.load(p); w = w.mean(0, keepdim=True)
    if sr != 16000: w = torchaudio.functional.resample(w, sr, 16000)
    f = torchaudio.compliance.kaldi.fbank(w, num_mel_bins=80, sample_frequency=16000, dither=0.0)
    f = f - f.mean(dim=0, keepdim=True)
    with torch.no_grad(): e = spk(f.unsqueeze(0))
    return torch.nn.functional.normalize(e, dim=-1)

BASE = {"音色基准_歌A": os.path.join(REFD, "c2925.wav"),
        "音色基准_歌B": os.path.join(REFD, "c6400.wav")}
E = {k: embed(v) for k, v in BASE.items() if os.path.exists(v)}
for r in rows: E[r["name"]] = embed(r["file"])
E["旧_带BGM"] = embed(r"D:\deepseek harness\ai-live\tts\try_12.wav")
E["旧_干净未去唱腔"] = embed(os.path.join(OUT, "clone_v2925.wav"))

print("\n=== 音色相似度（基准 = 原歌人声）===", flush=True)
for k in E:
    if k.startswith("音色基准"): continue
    a = float((E["音色基准_歌A"] @ E[k].T).item())
    b = float((E["音色基准_歌B"] @ E[k].T).item())
    print(f"  {k:<20} vs歌A {a:+.3f}   vs歌B {b:+.3f}   均 {(a+b)/2:+.3f}", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))