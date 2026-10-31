# -*- coding: utf-8 -*-
r"""campplus 说话人相似度：判断克隆音色到底像不像参考。"""
import os, sys, json
sys.path.insert(0, r"D:\index-tts")
import torch, torchaudio
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus

INDEX = r"D:\index-tts"
REFD  = r"D:\deepseek harness\ai-live\tts\refs"
OUT   = r"D:\deepseek harness\ai-live\tts\out"

spk = CAMPPlus(feat_dim=80, embedding_size=192).eval()
sd = torch.load(os.path.join(INDEX, "checkpoints", "hf_cache", "campplus_cn_common.bin"),
                map_location="cpu", weights_only=False)
missing, unexpected = spk.load_state_dict(sd, strict=False)
print("[load] missing=%d unexpected=%d" % (len(missing), len(unexpected)))
if missing[:3]: print("  missing:", missing[:3])

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

CAND = [
    ("REF_c6400_干净参考", os.path.join(REFD, "c6400.wav")),
    ("REF_c2925_干净参考", os.path.join(REFD, "c2925.wav")),
    ("SEG12_原始带BGM",    os.path.join(REFD, "seg12.wav")),
    ("GEN_clean6400",     os.path.join(OUT, "clone_v6400.wav")),
    ("GEN_clean2925",     os.path.join(OUT, "clone_v2925.wav")),
    ("GEN_bgm12",         r"D:\deepseek harness\ai-live\tts\try_12.wav"),
    ("GEN_bgm64",         r"D:\deepseek harness\ai-live\tts\try_64.wav"),
]
E = {}
for n, p in CAND:
    if os.path.exists(p):
        E[n] = embed(p)
    else:
        print("  缺失:", p)

print("\n=== 余弦相似度矩阵（1.000 = 同一人；<0.6 通常不像）===")
keys = list(E)
w = max(len(k) for k in keys)
print(" " * (w + 2) + "".join(f"{k[:14]:>16}" for k in keys))
for a in keys:
    row = f"{a:<{w}}  "
    for b in keys:
        s = float((E[a] @ E[b].T).item())
        row += f"{s:>16.3f}"
    print(row)

print("\n=== 关键对比 ===")
def cmp(a, b):
    if a in E and b in E:
        s = float((E[a] @ E[b].T).item())
        print(f"  {a:<20} vs {b:<20} {s:+.3f}")
cmp("REF_c6400_干净参考", "GEN_clean6400")
cmp("REF_c2925_干净参考", "GEN_clean2925")
cmp("SEG12_原始带BGM", "REF_c6400_干净参考")   # 分离前后同人基线
cmp("SEG12_原始带BGM", "GEN_bgm12")
cmp("REF_c6400_干净参考", "GEN_bgm12")
print("\n[baseline] 同一首歌不同段落之间的相似度就是『上限参考』:",
      round(float((E["REF_c6400_干净参考"] @ E["REF_c2925_干净参考"].T).item()), 3))