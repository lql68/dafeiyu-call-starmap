# -*- coding: utf-8 -*-
"""打两次 /api/say，确认新参考音频真的生效（时长、电平、缓存）。"""
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8770"


def say(text):
    req = urllib.request.Request(
        BASE + "/api/say",
        data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.loads(r.read().decode("utf-8"))
    return j, time.time() - t0


for t in ["爸爸，我看见你了，别动那么远嘛。", "爸爸，我看见你了，别动那么远嘛。"]:
    j, el = say(t)
    path = os.path.join(r"D:\deepseek harness\ai-live", j["url"].lstrip("/").replace("/", os.sep))
    size = os.path.getsize(path) if os.path.exists(path) else -1
    print("耗时 %5.2fs  dur=%s  cached=%s  %s  %d bytes" % (el, j.get("dur"), j.get("cached"), j["url"], size))
