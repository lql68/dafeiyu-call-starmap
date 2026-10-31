# -*- coding: utf-8 -*-
r"""对照分析：原混音 / 分离人声 / 伴奏，找最干净的人声窗口。"""
import sys, wave
sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np

SEP = r"D:\deepseek harness\ai-live\tts\sep\htdemucs\cover_full"

def load(p):
    with wave.open(p) as w:
        sr = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr

def report(name, a, sr, win=2.0):
    hop = int(win * sr)
    n = len(a) // hop
    rms = [float(np.sqrt((a[i*hop:(i+1)*hop] ** 2).mean())) for i in range(n)]
    print(f"\n=== {name}  sr={sr}  dur={len(a)/sr:.2f}s  peak={np.abs(a).max():.3f}  rms={np.sqrt((a**2).mean()):.4f}")
    print("  每2s RMS: " + " ".join(f"{v:.3f}" for v in rms))

def best_window(a, sr, span=10.0):
    """在 span 长度的滑窗里找 rms 最接近目标、且波动最小的段"""
    w = int(span * sr); hop = int(0.25 * sr)
    rows = []
    for s in range(0, len(a) - w, hop):
        seg = a[s:s+w]
        r = np.sqrt((seg**2).mean())
        # 抽 0.5s 子块的 RMS 波动
        sub = [np.sqrt((seg[i:i+sr//2]**2).mean()) for i in range(0, w-sr//2, sr//2)]
        rows.append((s/sr, r, float(np.std(sub)), float(np.percentile(np.abs(seg),99))))
    return rows

if __name__ == "__main__":
    voc, sr = load(SEP + r"\vocals.wav")
    acc, _ = load(SEP + r"\no_vocals.wav")
    mix, _ = load(r"D:\deepseek harness\ai-live\tts\refs\cover_full.wav")

    # 统一重采样到 24k 已经在 voc/acc；mix 也是 24k
    report("VOCALS(分离人声)", voc, sr)
    report("ACCOMP(伴奏)", acc, sr)

    print("\n--- 各段对伴奏的抑制比（人声段应 >> 1）")
    hop = sr * 2
    for i in range(min(len(voc), len(acc)) // hop):
        v = np.sqrt((voc[i*hop:(i+1)*hop]**2).mean())
        m = np.sqrt((acc[i*hop:(i+1)*hop]**2).mean())
        d = 20*np.log10((v+1e-9)/(m+1e-9))
        print(f"  {i*2:>3.0f}s  人声{v:.3f}  伴奏{m:.3f}  比{d:+.1f}dB")

    rows = best_window(voc, sr, 10.0)
    # 目标：响度够（rms>0.05）且子块波动小（连续唱而不是断断续续）
    cands = [r for r in rows if r[1] > 0.05]
    cands.sort(key=lambda r: r[2])
    print("\n--- 10s 窗口 Top8（按段内波动升序，rms>0.05）")
    for s, r, sd, p99 in cands[:8]:
        print(f"  start={s:>6.2f}s  rms={r:.3f}  sub_std={sd:.4f}  p99={p99:.2f}")