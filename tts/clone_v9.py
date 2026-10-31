# -*- coding: utf-8 -*-
r"""v9：拆开缓存四件套，音色条件用她的、节奏条件用 Huihui 的说话版。
   infer_v2_5.py:654-663 缓存字段：
     cache_spk_cond        = spk_cond_emb   (w2v-bert，音色+内容)
     cache_s2mel_style     = style          (campplus 192，纯音色)
     cache_s2mel_prompt    = prompt_condition(length_regulator 输出，定节奏/长度)
     cache_mel             = ref_mel        (mel 参考，定 s2mel 的时长分布)
   只要 cache_spk_audio_prompt 不变，走 else 分支就会直接用被换过的缓存。"""
import os, sys, time, wave, subprocess, json
sys.path.insert(0, r"D:\index-tts")
import torch

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
HER  = os.path.join(REFD, "her_timbre_breathed.wav")   # 音色最好(0.841)且已加换气
NEU  = os.path.join(REFD, "neutral_raw.wav")           # Huihui 说话，节奏基准
TEXT = "爸爸，我看见你了，别动那么远嘛。"

from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=r"D:\index-tts\checkpoints\config.yaml",
                model_dir=r"D:\index-tts\checkpoints", use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s  device={tts.device}", flush=True)

rows = []


def run(tag, spk_path, note=""):
    raw = os.path.join(OUT, f"_r9_{tag}.wav")
    ts = time.time()
    tts.infer(spk_audio_prompt=spk_path, text=TEXT, output_path=raw, lang="zh",
              stream_return=False, duration_factor=1.0)
    dst = os.path.join(OUT, f"v9_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", raw, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=tag, file=dst, dur=round(d, 2), cps=round(len(TEXT) / d, 2), note=note))
    print(f"[gen] v9_{tag}  dur={d:.2f}s  语速={len(TEXT)/d:.2f}字/秒  {note}", flush=True)


# ---------- 1. 预热她的 cache 并抓下来 ----------
run("base_her", HER, "全通道她（音色上限，节奏也她）")
spk_her = tts.cache_spk_cond.detach().clone()
sty_her = tts.cache_s2mel_style.detach().clone()
prm_her = tts.cache_s2mel_prompt.detach().clone()
mel_her = tts.cache_mel.detach().clone()
print(f"[cache] her  spk={tuple(spk_her.shape)} style={tuple(sty_her.shape)} "
      f"prompt={tuple(prm_her.shape)} mel={tuple(mel_her.shape)}", flush=True)

# ---------- 2. 预热 Huihui cache（节奏基准）----------
run("base_neu", NEU, "全通道 Huihui（音色跑偏，节奏说话）")
spk_neu = tts.cache_spk_cond.detach().clone()
sty_neu = tts.cache_s2mel_style.detach().clone()
print(f"[cache] neu  spk={tuple(spk_neu.shape)} style={tuple(sty_neu.shape)}", flush=True)

# 此刻 cache_spk_audio_prompt == NEU，prompt/mel 都是 Huihui 的说话版


def inject(spk, sty, use_her_rhythm=False):
    tts.cache_spk_cond = spk.to(tts.device)
    tts.cache_s2mel_style = sty.to(tts.device)
    if use_her_rhythm:
        tts.cache_s2mel_prompt = prm_her.to(tts.device)
        tts.cache_mel = mel_her.to(tts.device)
    else:
        tts.cache_s2mel_prompt = prm_neu_ref.to(tts.device)
        tts.cache_mel = mel_neu_ref.to(tts.device)


prm_neu_ref, mel_neu_ref = tts.cache_s2mel_prompt.detach().clone(), tts.cache_mel.detach().clone()

# ---------- 3. 三个对照 ----------
inject(spk_her, sty_her)
run("A_spk+sty_her_rhythm_neu", NEU, "音色=她(spk+style) 节奏=Huihui 【目标】")

inject(spk_neu, sty_her)
run("B_style_her_only", NEU, "只换 style=她（对照 v5 的 0.388）")

inject(spk_her, sty_neu)
run("C_spk_her_only", NEU, "只换 spk_cond=她，style 用 Huihui")

inject(spk_her, sty_her, use_her_rhythm=True)
run("D_her_rhythm_her_timbre", NEU, "音色=她 节奏也=她（应等于 base_her）")

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))