import sys, wave
SP = r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages"
if SP not in sys.path: sys.path.insert(0, SP)
import numpy as np
p = r"D:\deepseek harness\ai-live\tts\refs\cover_full.wav"
w = wave.open(p)
sr = w.getframerate(); n = w.getnframes()
x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)/32768.0
print("sr=%d  dur=%.2fs  peak=%.3f  rms=%.4f" % (sr, n/sr, np.abs(x).max(), np.sqrt((x**2).mean())))
win = int(sr*0.25)
frames = len(x)//win
r = np.sqrt((x[:frames*win].reshape(frames,win)**2).mean(axis=1))
# 打印每 2 秒的 RMS 概览
print("每2秒 RMS:")
line=[]
for i in range(0, frames, 8):
    line.append("%4.1fs:%.3f" % (i*0.25, r[i]))
    if len(line)==8: print("  " + "  ".join(line)); line=[]
if line: print("  " + "  ".join(line))
# 找最优 10 秒窗口：RMS 高且方差小（稳定人声，无突变）
best=None
for start in range(0, frames-40, 4):
    seg = r[start:start+40]
    m, s = seg.mean(), seg.std()
    if m < 0.06: continue
    score = m / (1 + s*3)
    if best is None or score > best[0]: best = (score, start)
print("最佳10s窗口: start=%.1fs score=%.4f mean=%.3f" % (best[1]*0.25, best[0], r[best[1]:best[1]+40].mean()))
