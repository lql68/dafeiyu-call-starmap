# -*- coding: utf-8 -*-
r"""v4：参数扫描去唱腔强度 k（音域压缩比）+ 颤音平滑窗，找「像她 + 说话感」的甜点。
一次加载模型跑完所有变体。"""
import os, sys, json, time, math, wave, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.signal import savgol_filter, medfilt
import torch, torchaudio

INDEX = r"D:\index-tts"
FF    = r"C:\Users\liu\bin\ffmpeg.exe"
SEP   = r"D:\deepseek harness\ai-live\tts\sep\htdemucs\cover_full\vocals.wav"
REFD  = r"D:\deepseek harness\ai-live\tts\refs"
OUT   = r"D:\deepseek harness\ai-live\tts\out"
os.makedirs(OUT, exist_ok=True)

TEXT = "爸爸，我看见你了，别动那么远嘛。"
FP   = 5.0
START, DUR = 29.25, 10.0

# (标签, 音域压缩k, 平滑ms, duration_factor)
GRID = [
    ("k40df085", 0.40, 120.0, 0.85),
    ("k60df085", 0.60, 120.0, 0.85),
    ("k60df100", 0.60, 120.0, 1.00),
]


def cut(start, dur, sr=16000):
    tmp = os.path.join(REFD, "_tmp_cut.wav")
    subprocess.run([FF, "-y", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", SEP,
                    "-ar", str(sr), "-ac", "1", tmp], check=True)
    x, s = sf.read(tmp, dtype="float64")
    return x, s


def devocal(x, sr, k, smooth_ms):
    f0, t = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=600.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    voiced = f0 > 0
    win = int(round(smooth_ms / FP)) | 1
    f0s = f0.copy()
    idx = np.where(voiced)[0]
    if len(idx) > win:
        f0s[idx] = savgol_filter(f0s[idx], win, 2)
        f0s[idx] = medfilt(f0s[idx], kernel_size=7)
    f0s[~voiced] = 0.0
    lf = np.log(np.maximum(f0s, 1e-6))
    med = float(np.median(lf[voiced]))
    f0n = np.where(voiced, np.exp(med + (lf - med) * k), 0.0)
    v = f0n[f0n > 0]
    span = 12 * math.log2(np.percentile(v, 95) / np.percentile(v, 5))
    y = pw.synthesize(f0n, sp, ap, sr, frame_period=FP).astype(np.float32)
    y = y / (np.abs(y).max() + 1e-9) * 0.85
    return y, sr, span, float(np.median(f0[voiced]))


def to24k(src_wav, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src_wav, "-ar", "24000", "-ac", "1",
                    "-af", "alimiter=limit=0.89:attack=3:release=40", dst], check=True)
    return dst


def norm(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    return dst


x, sr = cut(START, DUR)

# ---------- 1. 造参考 ----------
refs = []
for name, k, sm, df in GRID:
    y, s, span, med = devocal(x, sr, k, sm)
    tmp = os.path.join(REFD, f"_dv_{name}.wav")
    sf.write(tmp, y, s)
    ref = to24k(tmp, os.path.join(REFD, f"dv_{name}.wav"))
    refs.append((name, ref, df))
    print(f"[ref] {name}  k={k} smooth={sm}ms  原始中位 {med:.0f}Hz  处理后音域跨度 {span:.1f} 半音", flush=True)

# ---------- 2. 合成 ----------
from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=os.path.join(INDEX, "checkpoints", "config.yaml"),
                model_dir=os.path.join(INDEX, "checkpoints"),
                use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

rows = []
for name, ref, df in refs:
    raw = os.path.join(OUT, f"_r4_{name}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=ref, text=TEXT, output_path=raw, lang="zh",
              stream_return=False, duration_factor=df)
    cost = time.time() - ts
    dst = norm(raw, os.path.join(OUT, f"v4_{name}.wav"))
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=name, ref=ref, file=dst, cost=round(cost, 2),
                     dur=round(d, 2), cps=round(len(TEXT) / d, 2)))
    print(f"[gen] {name}  dur={d:.2f}s  语速={len(TEXT)/d:.2f}字/秒", flush=True)

torch.cuda.empty_cache()

# ---------- 3. 打分 ----------
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus
spk = CAMPPlus(feat_dim=80, embedding_size=192).eval()
spk.load_state_dict(torch.load(os.path.join(INDEX, "checkpoints", "hf_cache", "campplus_cn_common.bin"),
                               map_location="cpu", weights_only=False))

def embed(p):
    w, s = torchaudio.load(p); w = w.mean(0, keepdim=True)
    if s != 16000: w = torchaudio.functional.resample(w, s, 16000)
    f = torchaudio.compliance.kaldi.fbank(w, num_mel_bins=80, sample_frequency=16000, dither=0.0)
    f = f - f.mean(dim=0, keepdim=True)
    with torch.no_grad(): e = spk(f.unsqueeze(0))
    return torch.nn.functional.normalize(e, dim=-1)

E = {"歌A": embed(os.path.join(REFD, "c2925.wav")),
     "歌B": embed(os.path.join(REFD, "c6400.wav"))}
for r in rows: E[r["name"]] = embed(r["file"])
E["旧_未去唱腔"] = embed(os.path.join(OUT, "clone_v2925.wav"))

print("\n=== 音色相似度（基准=原歌人声）===", flush=True)
for k, v in E.items():
    if k in ("歌A", "歌B"): continue
    a = float((E["歌A"] @ v.T).item()); b = float((E["歌B"] @ v.T).item())
    print(f"  {k:<14} vs歌A {a:+.3f}  vs歌B {b:+.3f}  均 {(a+b)/2:+.3f}", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))