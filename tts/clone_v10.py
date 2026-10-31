# -*- coding: utf-8 -*-
r"""v10：spk 通道走 Huihui 的说话文件（ref_mel + prompt_condition = 说话节奏），
   emo 通道指向她的文件（emo_cond_emb = 音色）。扫 emo_alpha。"""
import os, sys, time, wave, subprocess, json
sys.path.insert(0, r"D:\index-tts")

FF   = r"C:\Users\liu\bin\ffmpeg.exe"
REFD = r"D:\deepseek harness\ai-live\tts\refs"
OUT  = r"D:\deepseek harness\ai-live\tts\out"
HER  = os.path.join(REFD, "her_timbre_breathed.wav")
HER2 = os.path.join(REFD, "c2925.wav")
NEU  = os.path.join(REFD, "neutral_raw.wav")
TEXT = "爸爸，我看见你了，别动那么远嘛。"

from indextts.infer_v2_5 import IndexTTS2
t0 = time.time()
tts = IndexTTS2(cfg_path=r"D:\index-tts\checkpoints\config.yaml",
                model_dir=r"D:\index-tts\checkpoints", use_bf16=True, use_cuda_kernel=False)
print(f"[load] {time.time()-t0:.1f}s", flush=True)

rows = []


def run(tag, spk, emo=None, alpha=1.0, df=1.0, note=""):
    raw = os.path.join(OUT, f"_r10_{tag}.wav")
    kw = dict(spk_audio_prompt=spk, text=TEXT, output_path=raw, lang="zh",
              stream_return=False, duration_factor=df)
    if emo is not None:
        kw.update(emo_audio_prompt=emo, emo_alpha=alpha)
    tts.infer(**kw)
    dst = os.path.join(OUT, f"v10_{tag}.wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", raw, "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89:attack=3:release=40",
                    "-ar", "24000", "-ac", "1", dst], check=True)
    with wave.open(dst) as w: d = w.getnframes() / w.getframerate()
    rows.append(dict(name=tag, file=dst, dur=round(d, 2), cps=round(len(TEXT) / d, 2), note=note))
    print(f"[gen] v10_{tag}  dur={d:.2f}s  {len(TEXT)/d:.2f}字/秒  {note}", flush=True)


for a in (0.6, 0.85, 1.0, 1.25):
    run(f"emo{a:.2f}", NEU, HER, a, note=f"spk=Huihui节奏 emo=她就 alpha={a}")

run("emo1.00_c2925", NEU, HER2, 1.0, note="emo 换成未加换气的 c2925")
run("emo1.00_df085", NEU, HER, 1.0, df=0.85, note="再压时长 0.85")
run("emo1.25_df080", NEU, HER, 1.25, df=0.80, note="alpha1.25 + df0.8")

print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))