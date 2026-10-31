# -*- coding: utf-8 -*-
"""量一下线上产出的音色/语速/唱腔。只加载 campplus（很小），不碰 TTS。"""
import os
import sys

import numpy as np
import soundfile as sf
import soundfile as sf
import torch
import torchaudio

sys.path.insert(0, r"D:\index-tts")
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus  # noqa: E402

INDEX = r"D:\index-tts"
ROOT = r"D:\deepseek harness\ai-live"
REFD = os.path.join(ROOT, "tts", "refs")

spk = CAMPPlus(feat_dim=80, embedding_size=192).eval()
sd = torch.load(os.path.join(INDEX, "checkpoints", "hf_cache", "campplus_cn_common.bin"),
                map_location="cpu", weights_only=False)
spk.load_state_dict(sd, strict=False)


def embed(p):
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


def report(tag, path, chars, ref):
    w, sr = sf.read(path)
    if w.ndim > 1:
        w = w.mean(1)
    dur = len(w) / sr
    print("%-16s %6.2fs  %4.2f字/秒  peak %.3f rms %.4f  相似度(vs新参考) %.3f"
          % (tag, dur, chars / dur, float(np.abs(w).max()),
             float(np.sqrt((w * w).mean())), sim(path, ref)))


NEW = os.path.join(REFD, "jiling.wav")
JUST = os.path.join(ROOT, "tts", "voice", "ec0b20e25281f6.wav")
OLD = os.path.join(ROOT, "tts", "out", "try_old.wav")
NEWT = os.path.join(ROOT, "tts", "out", "try_jiling.wav")

print("参考音频：", sf.info(NEW).duration, "s")
for tag, p in (("线上(机灵版+后处理)", JUST), ("直出(机灵版)", NEWT), ("旧参考+变速", OLD)):
    if os.path.exists(p):
        report(tag, p, 15, NEW)
    else:
        print("缺文件:", p)
