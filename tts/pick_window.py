# -*- coding: utf-8 -*-
"""从 jiling_full.wav 里挑一段连续的、少停顿的 8 秒，切成最终参考音频。"""
import sys
import wave

sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np  # noqa: E402

SRC = r"D:\deepseek harness\ai-live\tts\refs\jiling_full.wav"
DST = r"D:\deepseek harness\ai-live\tts\refs\jiling.wav"

w = wave.open(SRC)
sr = w.getframerate()
n = w.getnframes()
x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768

hop = sr // 10
rms = np.sqrt(np.convolve(x * x, np.ones(hop) / hop, "same"))[::hop]

best = None
WIN = 80            # 8 秒
for i in range(0, len(rms) - WIN):
    seg = rms[i:i + WIN]
    sil = int((seg < 0.012).sum())
    mean = float(seg.mean())
    score = -sil * 10 + mean          # 少静音优先，其次响度
    if best is None or score > best[0]:
        best = (score, i, sil, mean)

_, i, sil, mean = best
start = int(i * hop)
end = int((i + WIN) * hop)
seg = x[start:end]
print("挑中 %0.1fs-%0.1fs  静音格 %d/%d  mean rms %.4f" % (i * 0.1, (i + WIN) * 0.1, sil, WIN, mean))

# 头尾各收 80ms 淡入淡出，避免爆音
fade = int(0.08 * sr)
env = np.ones(len(seg), dtype=np.float32)
env[:fade] = np.linspace(0, 1, fade)
env[-fade:] = np.linspace(1, 0, fade)
seg = seg * env

# 归一化到 -3dBFS 左右
peak = float(np.abs(seg).max())
if peak > 0:
    seg = seg * (0.70 / peak)
print("输出 peak %.3f rms %.4f 时长 %.2fs" % (np.abs(seg).max(), np.sqrt((seg * seg).mean()), len(seg) / sr))

o = wave.open(DST, "wb")
o.setnchannels(1)
o.setsampwidth(2)
o.setframerate(sr)
o.writeframes((seg * 32767).astype(np.int16).tobytes())
o.close()
print("saved", DST)
