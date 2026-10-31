# -*- coding: utf-8 -*-
r"""最终版：全通道她的音色 + 波形域变速/换气后处理（factor 1.39，实测最优）。
   同时对短句和长段各做一遍，并拼 AB 对比带。"""
import os, sys, re, time, wave, subprocess, json
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import soundfile as sf

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
HER  = os.path.join(REFD, "her_timbre_breathed.wav")
FACTOR = 1.39
SR = 24000

TEXTS = {
    "短句": "爸爸，我看见你了，别动那么远嘛。",
    "长段": "爸爸，你终于接电话了。我今天在宿舍待了一整天，窗外的光一直变来变去。你那边现在几点了？",
}


def punct_positions(text):
    n = len(text)
    return [i / n for i, ch in enumerate(text) if ch in "，。？、；！"]


def post(src, text, tag, factor=FACTOR, pause_ms=70):
    with wave.open(src) as w:
        dur = w.getnframes() / w.getframerate()
    tmp = os.path.join(OUT, f"_f_{tag}_t.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af", f"atempo={factor:.4f}",
                    "-ar", str(SR), "-ac", "1", tmp], check=True)
    y, sr = sf.read(tmp, dtype="float64")
    y = y / (np.abs(y).max() + 1e-9) * 0.82

    g = np.zeros(int(sr * pause_ms / 1000))
    for c in sorted(punct_positions(text), reverse=True):
        p = int(len(y) * c)
        if 0 < p < len(y):
            y = np.concatenate([y[:p], g, y[p:]])

    y = y / (np.abs(y).max() + 1e-9) * 0.89
    raw = os.path.join(OUT, f"_f_{tag}.wav")
    sf.write(raw, y, sr)
    dst = os.path.join(OUT, f"final_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", raw, "-ar", "24000", "-ac", "1",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    dst], check=True)
    with wave.open(dst) as w:
        d = w.getnframes() / w.getframerate()
    print(f"[post] final_{tag}  {dur:.2f}s -> {d:.2f}s  ({len(text)/d:.2f}字/秒)", flush=True)
    return dst, d


from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=r"D:\index-tts\checkpoints\config.yaml",
                model_dir=r"D:\index-tts\checkpoints", use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

made = {}
for tag, text in TEXTS.items():
    raw = os.path.join(OUT, f"_f_{tag}_raw.wav")
    tts.infer(spk_audio_prompt=HER, text=text, output_path=raw, lang="zh",
              stream_return=False, duration_factor=1.0)
    dst, d = post(raw, text, tag)
    made[tag] = dict(file=dst, dur=round(d, 2), chars=len(text))

print("\n" + json.dumps(made, ensure_ascii=False, indent=1))