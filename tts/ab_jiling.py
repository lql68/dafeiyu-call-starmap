# -*- coding: utf-8 -*-
"""只用 numpy 量电平语速，并拼一条 AB 试听（原声参考 → 旧参考合成 → 新参考合成）。"""
import os
import subprocess
import sys
import wave

sys.path.insert(0, r"D:\deepseek harness\astrbot-lab\AstrBot\.venv\Lib\site-packages")
import numpy as np  # noqa: E402

ROOT = r"D:\deepseek harness\ai-live"
FF = r"C:\Users\liu\bin\ffmpeg.exe"


def stat(tag, p, chars=None):
    if not os.path.exists(p):
        print("缺:", p)
        return
    w = wave.open(p) if p.endswith(".wav") else None
    if w is None:
        print("跳过(非wav)", tag)
        return
    sr, n = w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    dur = n / sr
    line = "%-18s %6.2fs  peak %.3f  rms %.4f" % (tag, dur, np.abs(x).max(), np.sqrt((x * x).mean()))
    if chars:
        line += "  %4.2f 字/秒" % (chars / dur)
    print(line)


stat("参考 机灵版", os.path.join(ROOT, "tts", "refs", "jiling.wav"))
stat("旧参考 合成", os.path.join(ROOT, "tts", "out", "try_old.wav"), 15)
stat("机灵版 直出", os.path.join(ROOT, "tts", "out", "try_jiling.wav"), 15)
stat("机灵版 线上", os.path.join(ROOT, "tts", "voice", "ec0b20e25281f6.wav"), 15)

# AB：原声 3 秒 → 旧合成 → 新合成
ref = os.path.join(ROOT, "tts", "refs", "jiling.wav")
seg = os.path.join(ROOT, "tts", "out", "_refprev.wav")
subprocess.run([FF, "-y", "-v", "error", "-i", ref, "-t", "3.0", "-ar", "24000", "-ac", "1", seg], check=True)

parts = [seg, os.path.join(ROOT, "tts", "out", "try_old.wav"),
         os.path.join(ROOT, "tts", "voice", "ec0b20e25281f6.wav")]
parts = [p for p in parts if os.path.exists(p)]
lst = os.path.join(ROOT, "tts", "out", "_ab.txt")
with open(lst, "w", encoding="utf-8") as f:
    for p in parts:
        f.write("file '%s'\n" % p.replace("\\", "/"))
ab = os.path.join(ROOT, "tts", "out", "AB_机灵版.mp3")
subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-b:a", "160k", ab], check=True)
print("AB ->", ab, os.path.getsize(ab), "bytes")
