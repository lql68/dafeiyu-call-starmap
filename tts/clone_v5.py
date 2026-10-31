# -*- coding: utf-8 -*-
r"""v5：音色/韵律解耦。
IndexTTS 内部三路条件：
  style            = campplus(192d)  ← 纯音色
  spk_cond_emb     = w2v-bert        ← 音色+内容
  ref_mel / prompt = 参考的 mel      ← 音色+韵律（唱腔从这里漏进来）
做法：用中性说话声(Huihui)建 cache 拿到干净的韵律通道，再把 campplus style 换成她的，
      让 s2mel/GPT 只用她的音色、不用歌的韵律。"""
import os, sys, json, time, wave, subprocess
sys.path.insert(0, r"D:\index-tts")
import torch, torchaudio

INDEX   = r"D:\index-tts"
FF      = r"C:\Users\liu\bin\ffmpeg.exe"
REFD    = r"D:\deepseek harness\ai-live\tts\refs"
OUT     = r"D:\deepseek harness\ai-live\tts\out"
NEUTRAL = os.path.join(REFD, "neutral_raw.wav")      # Huihui 8.05s 正常说话
COVER   = os.path.join(REFD, "c2925.wav")            # 分离干净的歌人声（她的音色）
TEXT    = "爸爸，我看见你了，别动那么远嘛。"
os.makedirs(OUT, exist_ok=True)


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

dev = tts.device


def campplus_style(wav_path):
    """复刻 infer_v2_5.py:627-645 的 style 计算"""
    audio, sr = tts._load_and_cut_audio(wav_path, 15, False)
    a16 = torchaudio.transforms.Resample(sr, 16000)(audio)
    feat = torchaudio.compliance.kaldi.fbank(a16.to(dev), num_mel_bins=80, dither=0,
                                             sample_frequency=16000)
    feat = feat - feat.mean(dim=0, keepdim=True)
    with torch.no_grad():
        return tts.campplus_model(feat.unsqueeze(0))


# ---------- 第 1 步：用中性说话声建 cache（拿到干净的 ref_mel / spk_cond_emb）----------
warm = os.path.join(OUT, "_warm.wav")
tts.infer(spk_audio_prompt=NEUTRAL, text="热身一下。", output_path=warm, lang="zh",
          stream_return=False)
print(f"[cache] built from NEUTRAL  spk_prompt={tts.cache_spk_audio_prompt}", flush=True)

# ---------- 第 2 步：把 campplus style 换成她的 ----------
style_her = campplus_style(COVER)
style_neutral = tts.cache_s2mel_style
print(f"[style] her={tuple(style_her.shape)}  neutral={tuple(style_neutral.shape)}  "
      f"cos={float(torch.nn.functional.cosine_similarity(style_her, style_neutral).item()):+.3f}", flush=True)

# ---------- 对照 A：纯中性（确认 style 通道真的在起作用）----------
rawA = os.path.join(OUT, "_r5_A_neutral.wav")
tts.infer(spk_audio_prompt=NEUTRAL, text=TEXT, output_path=rawA, lang="zh", stream_return=False)
aFile = norm(rawA, os.path.join(OUT, "v5_A_纯Huihui.wav"))

# ---------- 实验 B：换 style → 她的音色 + 说话的韵律 ----------
tts.cache_s2mel_style = style_her          # cache_spk_audio_prompt 仍是 NEUTRAL，不会重算
rawB = os.path.join(OUT, "_r5_B_decoupled.wav")
ts = time.time()
tts.infer(spk_audio_prompt=NEUTRAL, text=TEXT, output_path=rawB, lang="zh", stream_return=False)
costB = time.time() - ts
bFile = norm(rawB, os.path.join(OUT, "v5_B_解耦.wav"))

rows = [dict(name="A_纯Huihui", file=aFile, dur=round(dur_of(aFile), 2),
             cps=round(len(TEXT)/dur_of(aFile), 2)),
        dict(name="B_解耦(她的音色+说话韵律)", file=bFile, dur=round(dur_of(bFile), 2),
             cps=round(len(TEXT)/dur_of(bFile), 2), cost=round(costB, 2))]
for r in rows:
    print(f"[out] {r['name']:<24} dur={r['dur']}s  语速={r['cps']}字/秒", flush=True)

# ---------- 打分 ----------
torch.cuda.empty_cache()
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

E = {"歌A(她)": embed(os.path.join(REFD, "c2925.wav")),
     "歌B(她)": embed(os.path.join(REFD, "c6400.wav")),
     "Huihui": embed(NEUTRAL)}
E["v5_A_纯Huihui"] = embed(aFile)
E["v5_B_解耦"] = embed(bFile)
E["v4_k40(去唱腔参考)"] = embed(os.path.join(OUT, "v4_k40df085.wav"))
E["旧_未处理"] = embed(os.path.join(OUT, "clone_v2925.wav"))

print("\n=== 音色相似度（基准 = 原歌人声）===", flush=True)
for k, v in E.items():
    if k in ("歌A(她)", "歌B(她)", "Huihui"): continue
    a = float((E["歌A(她)"] @ v.T).item()); b = float((E["歌B(她)"] @ v.T).item())
    h = float((E["Huihui"] @ v.T).item())
    print(f"  {k:<22} vs歌A {a:+.3f}  vs歌B {b:+.3f}  均 {(a+b)/2:+.3f}   vsHuihui {h:+.3f}", flush=True)
print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))