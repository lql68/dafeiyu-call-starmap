"""用本地 ComfyUI（WAI Illustrious SDXL）出「暖色房间」背景图。

只接受一个参数：想要几张。每张换 seed，输出落在 ComfyUI 的 output 目录，
前缀 ai_live_bg。跑完打印每张的绝对路径。
"""

import json
import os
import sys
import time
import urllib.request

API = "http://127.0.0.1:8188"
OUT_DIR = r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\output"
PREFIX = "ai_live_bg"

PROMPT = (
    "no humans, empty room interior, cozy bedroom at night, "
    "tall wooden bookshelf filled with books on the left, "
    "warm desk lamp glow on the right, soft moonlight from upper right, "
    "wooden floor, a few books stacked on the desk, "
    "shallow depth of field, heavy bokeh, soft focus background, "
    "cinematic warm brown palette, dust particles floating in light, "
    "quiet lonely atmosphere, visual novel background art, "
    "detailed scenery, painterly, masterpiece, best quality"
)
NEG = (
    "people, person, human, 1girl, 1boy, character, face, hands, "
    "text, watermark, signature, logo, username, ui, border, frame, "
    "lowres, bad anatomy, blurry, jpeg artifacts, oversaturated, neon, "
    "harsh contrast, cluttered"
)

W, H = 1344, 768
STEPS = 30
CFG = 6.0


def graph(seed):
    return {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "waiIllustriousSDXL_v160.safetensors"}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": W, "height": H, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": PROMPT, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": NEG, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": STEPS, "cfg": CFG,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras",
                         "denoise": 1.0, "model": ["4", 0],
                         "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0], "filename_prefix": PREFIX}},
    }


def post(path, obj):
    req = urllib.request.Request(
        API + path, json.dumps(obj).encode(),
        {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def wait(pid, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            h = json.loads(urllib.request.urlopen(
                API + "/history/" + pid, timeout=20).read())
        except Exception:
            h = {}
        if pid in h and h[pid].get("outputs"):
            files = []
            for node in h[pid]["outputs"].values():
                for im in node.get("images", []):
                    files.append(os.path.join(
                        OUT_DIR, im.get("subfolder", ""), im["filename"]))
            if files:
                return files, time.time() - t0
        time.sleep(2)
    return [], time.time() - t0


n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
seeds = [20261101 + i * 977 for i in range(n)]

got = []
for i, sd in enumerate(seeds):
    print("出第 %d/%d 张  seed=%d …" % (i + 1, n, sd), flush=True)
    r = post("/prompt", {"prompt": graph(sd), "client_id": "ai-live-bg"})
    pid = r.get("prompt_id")
    if not pid:
        print("  提交失败:", r)
        continue
    files, dt = wait(pid)
    for f in files:
        print("  %.1fs -> %s" % (dt, f))
        got.append(f)

print("\n共 %d 张：" % len(got))
for f in got:
    print(" ", f, os.path.getsize(f) // 1024, "KB" if os.path.exists(f) else "")
