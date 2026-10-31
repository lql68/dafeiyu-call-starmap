# -*- coding: utf-8 -*-
"""检查新的参考音频：电平、静音分布、能量曲线。"""
import sys
import wave

sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np

p = r"D:\deepseek harness\ai-live\tts\refs\jiling_full.wav"
w = wave.open(p)
sr, n = w.getframerate(), w.getnframes()
x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
print("sr=%d dur=%.2fs peak=%.3f rms=%.4f" % (sr, n / sr, np.abs(x).max(), np.sqrt((x * x).mean())))

hop = sr // 10
r = np.sqrt(np.convolve(x * x, np.ones(hop) / hop, "same"))[::hop]
print("每0.1s rms: min %.4f 中位 %.4f max %.4f" % (r.min(), np.median(r), r.max()))
print("静音格 (<0.01): %d / %d" % ((r < 0.01).sum(), len(r)))

for i in range(0, max(1, len(r) - 19), 20):
    seg = r[i:i + 20]
    print("  %5.1fs-%5.1fs  mean %.4f  min %.4f" % (i * 0.1, (i + 20) * 0.1, seg.mean(), seg.min()))
