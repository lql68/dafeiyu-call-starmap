# -*- coding: utf-8 -*-
r"""用 demucs 分离后的干净人声做克隆参考，对比合成。"""
import os, sys, time, json

INDEX = r"D:\index-tts"
os.chdir(INDEX)
sys.path.insert(0, INDEX)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from indextts.infer_v2_5 import IndexTTS2

REFS = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
os.makedirs(OUT, exist_ok=True)

TEXT = "爸爸，我看见你了，别动那么远嘛。"

JOBS = [
    ("v2925", os.path.join(REFS, "v2925.wav")),
    ("v6400", os.path.join(REFS, "v6400.wav")),
]

t0 = time.time()
tts = IndexTTS2(
    cfg_path=os.path.join(INDEX, "checkpoints", "config.yaml"),
    model_dir=os.path.join(INDEX, "checkpoints"),
    use_bf16=True,
    use_cuda_kernel=False,
)
print(f"[load] {time.time()-t0:.2f}s  vram={torch.cuda.memory_allocated()/1e9:.2f}GB", flush=True)
print(f"[text] {TEXT}  ({len(TEXT)} 字)", flush=True)

rows = []
for tag, ref in JOBS:
    dst = os.path.join(OUT, f"cl_{tag}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=ref, text=TEXT, output_path=dst, lang="zh", stream_return=False)
    dt = time.time() - ts
    import wave
    with wave.open(dst) as w:
        dur = w.getnframes() / w.getframerate()
        sr = w.getframerate()
    rows.append(dict(tag=tag, cost=round(dt, 2), dur=round(dur, 2), sr=sr, file=dst))
    print(f"[gen] {tag}  cost={dt:.2f}s  dur={dur:.2f}s  sr={sr}", flush=True)

print("[peak] vram=%.2fGB" % (torch.cuda.max_memory_allocated()/1e9), flush=True)
print(json.dumps(rows, ensure_ascii=False, indent=1), flush=True)