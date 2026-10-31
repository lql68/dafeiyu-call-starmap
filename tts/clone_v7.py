# -*- coding: utf-8 -*-
r"""v7：真正的「只取音色」——跨说话人 WORLD 拼装。
  谱包络 sp = 音色（取自她）    f0 + ap + 停顿 = 韵律（取自 Huihui 的正常说话）
  把她的 sp 沿时间轴重采样到 Huihui 的帧数，再用 Huihui 的 f0/ap 驱动重合成。
  得到「同一个人用说话节奏发音」的音频，作为 IndexTTS 的参考。"""
import os, sys, math, time, wave, subprocess, json
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf
import pyworld as pw
from scipy.ndimage import zoom

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
SEP  = r"D:\deepseek harness\ai-live\tts\sep\htdemucs\cover_full\vocals.wav"
FP   = 5.0


def load(p, sr=16000, ss=None, t=None):
    tmp = os.path.join(REFD, "_t.wav")
    cmd = [FF, "-y", "-v", "error"]
    if ss is not None: cmd += ["-ss", str(ss)]
    if t is not None:  cmd += ["-t", str(t)]
    cmd += ["-i", p, "-ar", str(sr), "-ac", "1", tmp]
    subprocess.run(cmd, check=True)
    x, s = sf.read(tmp, dtype="float64")
    return x, s


def world(x, sr):
    f0, t = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=700.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    return f0, sp, ap


def retime(sp, T):
    """把 sp 的帧数重采样到 T 帧（音色不变，只是时间轴伸缩）"""
    if sp.shape[0] == T: return sp
    return zoom(sp, (T / sp.shape[0], 1.0), order=1)


print("[1] 分解她的歌（取 sp=音色）", flush=True)
xh, srh = load(SEP, ss=29.25, t=10.0)
f0h, sph, aph = world(xh, srh)
print(f"    her  sp={sph.shape}  f0中位={np.median(f0h[f0h>0]):.0f}Hz", flush=True)

print("[2] 分解 Huihui（取 f0/ap/停顿=韵律）", flush=True)
xn, srn = load(os.path.join(REFD, "neutral_raw.wav"))
f0n, spn, apn = world(xn, srn)
print(f"    neutral sp={spn.shape}  f0中位={np.median(f0n[f0n>0]):.0f}Hz  浊音={np.mean(f0n>0)*100:.0f}%", flush=True)

print("[3] 拼装：她的音色 + 中性说话的节奏", flush=True)
T = len(f0n)
sph2 = retime(sph, T)
y = pw.synthesize(f0n, sph2, apn, srn, frame_period=FP).astype(np.float32)
y = y / (np.abs(y).max() + 1e-9) * 0.85
raw = os.path.join(REFD, "_world_mix.wav")
sf.write(raw, y, srn)
ref = os.path.join(REFD, "mix_her_timbre_neutral_rhythm.wav")
subprocess.run([FF, "-y", "-v", "error", "-i", raw, "-ar", "24000", "-ac", "1",
                "-af", "alimiter=limit=0.89:attack=3:release=40", ref], check=True)
print(f"    -> {ref}  {len(y)/srn:.2f}s", flush=True)

# 也做一版：只把她的长 voiced 段切断（保留她的 f0，但插入静音）
print("[4] 备选版：保留她的 f0，插人换气静音", flush=True)
f0c = f0h.copy()
vr = f0h > 0
run, cuts = 0, []
for i, v in enumerate(vr):
    if v: run += 1
    else:
        run = 0
    if run == int(1.1 / (FP / 1000)):   # 连续浊音超过 1.1s 就开一个 60ms 静音
        n = int(0.06 / (FP / 1000))
        for k in range(i + 1, min(i + 1 + n, len(f0c))): f0c[k] = 0.0
        run = 0
y2 = pw.synthesize(f0c, sph, aph, srh, frame_period=FP).astype(np.float32)
y2 = y2 / (np.abs(y2).max() + 1e-9) * 0.85
raw2 = os.path.join(REFD, "_her_breath.wav")
sf.write(raw2, y2, srh)
ref2 = os.path.join(REFD, "her_timbre_breathed.wav")
subprocess.run([FF, "-y", "-v", "error", "-i", raw2, "-ar", "24000", "-ac", "1",
                "-af", "alimiter=limit=0.89:attack=3:release=40", ref2], check=True)
print(f"    -> {ref2}", flush=True)

# ---------- 合成 ----------
from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=os.path.join(os.sys.modules and r"D:\index-tts", "checkpoints", "config.yaml"),
                model_dir=r"D:\index-tts\checkpoints", use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

TEXT = "爸爸，我看见你了，别动那么远嘛。"
rows = []
for tag, refp, df in [("mix_中性节奏", ref, 1.00), ("her_加换气", ref2, 0.90)]:
    rawp = os.path.join(OUT, f"_r7_{tag}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=refp, text=TEXT, output_path=rawp, lang="zh",
              stream_return=False, duration_factor=df)
    dst = os.path.join(OUT, f"v7_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", rawp, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=tag, file=dst, dur=round(d, 2), cps=round(len(TEXT)/d, 2),
                     cost=round(time.time()-ts, 2)))
    print(f"[gen] {tag}  dur={d:.2f}s  语速={len(TEXT)/d:.2f}字/秒", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))