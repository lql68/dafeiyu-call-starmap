"""用 VoxCPM2 做零样本音色克隆，和 IndexTTS 同句对比。

跑法（必须用 voxcpm2 自己的 venv）：
  C:\\Users\\liu\\AppData\\Roaming\\OmniVoice\\engines\\voxcpm2\\voxcpm2\\.venv\\Scripts\\python.exe vox_test.py
"""
import os
import time
import wave

os.environ.setdefault("HF_HOME", r"C:\Users\liu\AppData\Local\OmniVoice\hf_cache")

import numpy as np
import torch
from voxcpm import VoxCPM

TEXT = "爸爸，我看见你了，别动那么远嘛。"
REF = r"D:\deepseek harness\ai-live\tts\refs\jiling.wav"
PROMPT_TEXT = "谁是吃大饭的大肥鱼啊，我刚才明明在认真思考，只是肚子有一点点饿嘛"
OUT = r"D:\deepseek harness\ai-live\tts\compare"


def save(path, arr, sr):
    a = np.asarray(arr, dtype=np.float32).reshape(-1)
    pk = float(np.abs(a).max() or 0.0)
    if pk > 0:
        a = a / pk * 0.92
    w = wave.open(path, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(int(sr))
    w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
    w.close()
    return len(a) / sr


def main():
    t0 = time.time()
    m = VoxCPM.from_pretrained("openbmb/VoxCPM2")
    load = time.time() - t0
    sr = int(getattr(m, "sample_rate", 16000) or 16000)
    print(f"[load] {load:.1f}s  sample_rate={sr}  vram={torch.cuda.memory_allocated()/1024**3:.2f}GB")

    # 1) 零样本克隆：只给参考音频（不给 prompt_text）
    for tag, kw in (
        ("clone_ref", dict(reference_wav_path=REF)),
    ):
        try:
            t = time.time()
            wav = m.generate(text=TEXT, **kw)
            dur = save(os.path.join(OUT, f"vox_{tag}.wav"), wav, sr)
            print(f"[{tag}] 全量 {time.time()-t:.2f}s  音频 {dur:.2f}s")
        except Exception as e:  # noqa: BLE001
            print(f"[{tag}] 失败: {type(e).__name__}: {e}")

    # 2) 流式：测首包
    try:
        t = time.time()
        first = None
        chunks = []
        for piece in m.generate_streaming(text=TEXT, reference_wav_path=REF):
            if first is None:
                first = time.time() - t
            chunks.append(np.asarray(piece, dtype=np.float32).reshape(-1))
        if chunks:
            wav = np.concatenate(chunks)
            dur = save(os.path.join(OUT, "vox_stream.wav"), wav, sr)
            print(f"[stream] 首包 {first:.2f}s 全量 {time.time()-t:.2f}s 音频 {dur:.2f}s 块 {len(chunks)}")
    except Exception as e:  # noqa: BLE001
        print(f"[stream] 失败: {type(e).__name__}: {e}")

    print(f"[vram] peak={torch.cuda.max_memory_allocated()/1024**3:.2f}GB")


main()
