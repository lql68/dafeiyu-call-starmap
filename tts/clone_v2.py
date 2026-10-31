# -*- coding: utf-8 -*-
r"""v2：参考音频响度对齐（不用 loudnorm 压死）→ 合成 → 输出归一 → campplus 说话人相似度打分。"""
import os, sys, json, time, math, wave, subprocess

sys.path.insert(0, r"D:\index-tts")
import numpy as np
import torch, torchaudio

INDEX = r"D:\index-tts"
FF    = r"C:\Users\liu\bin\ffmpeg.exe"
REFD  = r"D:\deepseek harness\ai-live\tts\refs"
OUT   = r"D:\deepseek harness\ai-live\tts\out"
SEP   = r"D:\deepseek harness\ai-live\tts\sep\htdemucs\cover_full\vocals.wav"
os.makedirs(OUT, exist_ok=True)

TEXT = "爸爸，我看见你了，别动那么远嘛。"


def rms_of(p):
    with wave.open(p) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1: a = a.reshape(-1, w.getnchannels()).mean(1)
    return float(np.sqrt((a ** 2).mean()))


def make_ref(start, dur, tag, target_db=-15.0):
    """切段 + 精确增益到 target_db RMS + 峰值限幅"""
    raw = os.path.join(REFD, f"_raw_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", SEP,
                    "-ar", "24000", "-ac", "1", raw], check=True)
    r = rms_of(raw)
    gain_db = target_db - 20 * math.log10(max(r, 1e-9))
    dst = os.path.join(REFD, f"{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", raw, "-af",
                    f"volume={gain_db:.2f}dB,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    r2 = rms_of(dst)
    print(f"[ref] {tag}  start={start}s  rms {r:.4f}({20*math.log10(r):.1f}dB) -> {r2:.4f}({20*math.log10(r2):.1f}dB)  gain={gain_db:+.2f}dB", flush=True)
    return dst


# ---------- 1. 参考 ----------
REFS = [
    ("v6400", make_ref(64.0, 10.0, "c6400")),   # 最响、伴奏抑制最好
    ("v2925", make_ref(29.25, 10.0, "c2925")),  # 段内最平稳
]

# ---------- 2. 合成 ----------
from indextts.infer_v2_5 import IndexTTS2

t0 = time.time()
tts = IndexTTS2(cfg_path=os.path.join(INDEX, "checkpoints", "config.yaml"),
                model_dir=os.path.join(INDEX, "checkpoints"),
                use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.2f}s  vram={torch.cuda.memory_allocated()/1e9:.2f}GB", flush=True)

gens = []
for tag, ref in REFS:
    raw = os.path.join(OUT, f"_raw_{tag}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=ref, text=TEXT, output_path=raw, lang="zh", stream_return=False)
    cost = time.time() - ts
    # 输出归一：峰值拉到 -1.5dB，并压到 -16 LUFS 附近
    dst = os.path.join(OUT, f"clone_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", raw,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    with wave.open(dst) as w:
        dur = w.getnframes() / w.getframerate()
    gens.append(dict(tag=tag, ref=ref, file=dst, cost=round(cost, 2), dur=round(dur, 2)))
    print(f"[gen] {tag}  cost={cost:.2f}s  dur={dur:.2f}s -> {dst}", flush=True)

torch.cuda.empty_cache()

# ---------- 3. campplus 说话人相似度 ----------
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus

spk = CAMPPlus(feat_dim=80, embedding_size=512).eval()
sd = torch.load(os.path.join(INDEX, "checkpoints", "hf_cache", "campplus_cn_common.bin"),
                map_location="cpu", weights_only=False)
spk.load_state_dict(sd)


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


E = {}
for name, p in [("REF_c6400", REFS[0][1]), ("REF_c2925", REFS[1][1]),
                ("GEN_c6400", gens[0]["file"]), ("GEN_c2925", gens[1]["file"]),
                ("SEG12_带BGM", os.path.join(REFD, "seg12.wav")),
                ("TRY12_带BGM生成", r"D:\deepseek harness\ai-live\tts\try_12.wav")]:
    if os.path.exists(p):
        E[name] = embed(p)

print("\n=== 说话人余弦相似度 ===", flush=True)
keys = list(E)
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        s = float((E[keys[i]] @ E[keys[j]].T).item())
        print(f"  {keys[i]:<18} vs {keys[j]:<18} {s:+.3f}", flush=True)

print("\n" + json.dumps(gens, ensure_ascii=False, indent=1))