# -*- coding: utf-8 -*-
"""用新的参考音频（大肥鱼机灵版）合成一句，跟旧参考比音色/唱腔。

跑法：D:\index-tts\.venv\Scripts\python.exe try_jiling.py
"""
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, r"D:\index-tts")
from indextts.infer_v2_5 import IndexTTS2  # noqa: E402
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus  # noqa: E402

INDEX = r"D:\index-tts"
ROOT = r"D:\deepseek harness\ai-live"
REFD = os.path.join(ROOT, "tts", "refs")
OUTD = os.path.join(ROOT, "tts", "out")
os.makedirs(OUTD, exist_ok=True)

NEW_REF = os.path.join(REFD, "jiling.wav")
OLD_REF = os.path.join(REFD, "her_timbre_breathed.wav")
TEXT = "爸爸，我看见你了，别动那么远嘛。"

t0 = time.time()
tts = IndexTTS2(cfg_path=os.path.join(INDEX, "checkpoints", "config.yaml"),
                model_dir=os.path.join(INDEX, "checkpoints"),
                use_bf16=True, use_cuda_kernel=False)
print("模型就绪 %.1fs" % (time.time() - t0))

# ── 相似度 ──
spk = CAMPPlus(feat_dim=80, embedding_size=192).eval()
sd = torch.load(os.path.join(INDEX, "checkpoints", "hf_cache", "campplus_cn_common.bin"),
                map_location="cpu", weights_only=False)
spk.load_state_dict(sd, strict=False)


def embed(p):
    import torchaudio
    w, sr = torchaudio.load(p)
    w = w.mean(0, keepdim=True)
    if sr != 16000:
        w = torchaudio.functional.resample(w, sr, 16000)
    f = torchaudio.compliance.kaldi.fbank(w, num_mel_bins=80, sample_frequency=16000, dither=0.0)
    f = f - f.mean(dim=0, keepdim=True)
    with torch.no_grad():
        e = spk(f.unsqueeze(0))
    return torch.nn.functional.normalize(e, dim=-1)


def sim(a, b):
    return float((embed(a) * embed(b)).sum())


def sing_index(p):
    """长音占比 / 停顿 / 浊音占比，越像唱歌越接近 1。"""
    import pyworld as pw
    w, sr = sf.read(p)
    if w.ndim > 1:
        w = w.mean(1)
    w = w.astype(np.float64)
    f0, t = pw.harvest(w, sr, f0_floor=70, f0_ceil=700, frame_period=10)
    f0 = pw.stonemask(w, f0, t, sr)
    v = f0 > 0
    # 长音：>=0.8s 连续浊音占浊音帧比例
    run = best = 0
    for x in v:
        run = run + 1 if x else 0
        best = max(best, run)
    longn = best / max(1, v.sum())
    hop = int(sr * 0.01)
    e = np.sqrt(np.convolve(w * w, np.ones(hop) / hop, "same"))[::hop]
    thr = max(0.01, np.percentile(e, 20) * 0.4)
    pauses = ((e < thr).sum()) / (len(e) / 100)
    return longn, pauses, v.mean()


for tag, ref in (("新_机灵版", NEW_REF), ("旧_加换气", OLD_REF)):
    dst = os.path.join(OUTD, "try_%s.wav" % ("jiling" if "机灵" in tag else "old"))
    t1 = time.time()
    tts.infer(spk_audio_prompt=ref, text=TEXT, output_path=dst, lang="zh", verbose=False)
    el = time.time() - t1
    info = sf.info(dst)
    w, _ = sf.read(dst)
    ln, pa, vo = sing_index(dst)
    s_ref = sim(dst, ref)
    print("[%s] %.2fs 合成耗时 %.2fs peak=%.3f rms=%.4f 相似度(vs自身参考)=%.3f 长音=%.2f 停顿/秒=%.2f 浊音=%.2f"
          % (tag, info.duration, el, float(np.abs(w).max()),
             float(np.sqrt((w * w).mean())), s_ref, ln, pa, vo))

# 新旧参考本身像不像
print("两个参考的相似度 = %.3f" % sim(NEW_REF, OLD_REF))
