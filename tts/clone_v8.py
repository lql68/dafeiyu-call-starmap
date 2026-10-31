# -*- coding: utf-8 -*-
r"""v8：只取音色 —— 谱包络均值差分（spectral envelope mean transfer）。
  不用整段歌做参考（会带唱腔），而是：
    1. 取她的 log 谱包络均值  mean_she
    2. 取中性说话声的 log 谱包络均值 mean_neu
    3. delta = mean_she - mean_neu
    4. 把中性说话声的每一帧谱包络加上 delta → 音素序列完全不变，只把音色搬过去
  得到「她的音色 + 100% 说话韵律」的参考，再交给 IndexTTS。"""
import os, sys, math, time, wave, subprocess, json
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
SEP  = r"D:\deepseek harness\ai-live\tts\sep\htdemucs\cover_full\vocals.wav"
FP   = 5.0


def load(p, sr=16000, ss=None, t=None):
    tmp = os.path.join(REFD, "_t8.wav")
    cmd = [FF, "-y", "-v", "error"]
    if ss is not None: cmd += ["-ss", str(ss)]
    if t is not None:  cmd += ["-t", str(t)]
    cmd += ["-i", p, "-ar", str(sr), "-ac", "1", tmp]
    subprocess.run(cmd, check=True)
    return sf.read(tmp, dtype="float64")


def world(x, sr):
    f0, t = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=700.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, t, sr)
    return f0, pw.cheaptrick(x, f0, t, sr), pw.d4c(x, f0, t, sr)


def to24(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-ar", "24000", "-ac", "1",
                    "-af", "alimiter=limit=0.89:attack=3:release=40", dst], check=True)
    return dst


print("[1] WORLD 分解", flush=True)
xh, srh = load(SEP, ss=29.25, t=10.0)
f0h, sph, aph = world(xh, srh)
xn, srn = load(os.path.join(REFD, "neutral_raw.wav"))
f0n, spn, apn = world(xn, srn)
print(f"    her sp={sph.shape}   neutral sp={spn.shape}", flush=True)

# ---------- 谱包络均值差分 ----------
ls_her = np.log(np.maximum(sph, 1e-8))
ls_neu = np.log(np.maximum(spn, 1e-8))
delta = ls_her.mean(0) - ls_neu.mean(0)
print(f"[2] delta 谱形统计: mean={delta.mean():+.3f} std={delta.std():.3f} "
      f"max={delta.max():+.2f}@bin{int(np.argmax(delta))}", flush=True)

variants = {}
# A：只搬音色（log 域加 delta）
variants["mean"] = np.exp(ls_neu + delta)
# B：搬音色 + 强度随频率衰减（保护低频基频区，避免嗡嗡）
w = np.ones(ls_neu.shape[1])
w[:6] = 0.3
variants["mean_lofix"] = np.exp(ls_neu + delta * w)
# C：一半强度（保守）
variants["half"] = np.exp(ls_neu + delta * 0.55)

for tag, sp in variants.items():
    y = pw.synthesize(f0n, sp, apn, srn, frame_period=FP).astype(np.float32)
    y = y / (np.abs(y).max() + 1e-9) * 0.85
    raw = os.path.join(REFD, f"_vc_{tag}.wav")
    sf.write(raw, y, srn)
    ref = to24(raw, os.path.join(REFD, f"vc_{tag}.wav"))
    print(f"[3] 参考 vc_{tag} -> {ref}", flush=True)

# ---------- 合成 ----------
from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=r"D:\index-tts\checkpoints\config.yaml",
                model_dir=r"D:\index-tts\checkpoints", use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

TEXT = "爸爸，我看见你了，别动那么远嘛。"
rows = []
for tag in ["mean", "mean_lofix", "half"]:
    refp = os.path.join(REFD, f"vc_{tag}.wav")
    rawp = os.path.join(OUT, f"_r8_{tag}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=refp, text=TEXT, output_path=rawp, lang="zh",
              stream_return=False, duration_factor=1.0)
    dst = os.path.join(OUT, f"v8_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", rawp, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=tag, file=dst, dur=round(d, 2), cps=round(len(TEXT)/d, 2)))
    print(f"[gen] v8_{tag}  dur={d:.2f}s  语速={len(TEXT)/d:.2f}字/秒", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))