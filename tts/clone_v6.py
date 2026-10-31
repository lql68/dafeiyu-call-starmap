# -*- coding: utf-8 -*-
r"""v6：不再只动 f0，改「节奏结构」。用分段 + 段间静音把拖长音打断，
制造说话的换气与句读。参考固定用 WORLD 处理后的 dv_k40df085（音色 0.709）。"""
import os, sys, json, time, wave, subprocess
sys.path.insert(0, r"D:\index-tts")
import numpy as np
import torch, torchaudio

INDEX = r"D:\index-tts"
FF    = r"C:\Users\liu\bin\ffmpeg.exe"
REFD  = r"D:\deepseek harness\ai-live\tts\refs"
OUT   = r"D:\deepseek harness\ai-live\tts\out"
REF   = os.path.join(REFD, "dv_k40df085.wav")

TEXT = "爸爸，我看见你了，别动那么远嘛。"

# (标签, max_text_tokens_per_segment, interval_silence, duration_factor, 文本)
JOBS = [
    ("seg12_sil300", 12, 300, 0.90, TEXT),
    ("seg8_sil350",   8, 350, 0.90, TEXT),
    ("seg6_sil400",   6, 400, 0.90, TEXT),
]


def norm(src, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    return dst


def dur_of(p):
    with wave.open(p) as w: return w.getnframes() / w.getframerate()


from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=os.path.join(INDEX, "checkpoints", "config.yaml"),
                model_dir=os.path.join(INDEX, "checkpoints"),
                use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

rows = []
for tag, mx, sil, df, txt in JOBS:
    raw = os.path.join(OUT, f"_r6_{tag}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=REF, text=txt, output_path=raw, lang="zh",
              stream_return=False, duration_factor=df,
              max_text_tokens_per_segment=mx, interval_silence=sil)
    cost = time.time() - ts
    dst = norm(raw, os.path.join(OUT, f"v6_{tag}.wav"))
    d = dur_of(dst)
    rows.append(dict(name=tag, file=dst, cost=round(cost, 2), dur=round(d, 2),
                     cps=round(len(txt) / d, 2), mx=mx, sil=sil, df=df))
    print(f"[gen] {tag}  dur={d:.2f}s  语速={len(txt)/d:.2f}字/秒", flush=True)

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))