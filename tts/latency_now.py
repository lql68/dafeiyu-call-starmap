"""量一下现在「说完到听见」到底多少秒（整段播放这条路）。

只打 HTTP，不动页面：
  think  -> POST /api/think  （AstrBot 大肥鱼人格 + 记忆）
  synth  -> POST /api/say    （IndexTTS 整段合成）
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8770"

SAMPLES = [
    "我今天加班到现在，头有点疼",
    "你在干嘛呀",
    "外面下雨了，我伞忘在公司了",
]


def post(path, obj, timeout=240):
    body = json.dumps(obj, ensure_ascii=False).encode()
    req = urllib.request.Request(BASE + path, body, {"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return time.time() - t, data


print("句  |  think(s)  |  synth(s)  |  合计  | 音频  | 回复")
print("-" * 88)
tot = []
for heard in SAMPLES:
    tt, tj = post("/api/think", {"heard": heard, "state": {}})
    line = (tj.get("text") or "").strip()
    if not line:
        print(f"{heard[:10]} | think 失败 {tj}")
        continue
    ts, sj = post("/api/say", {"text": line, "mirror": False})
    dur = sj.get("dur") or 0
    tot.append(tt + ts)
    print(f"{heard[:10]} |  {tt:5.2f}  |  {ts:5.2f}  | {tt+ts:5.2f}s | {dur:4.2f}s | {line}")

if tot:
    print("-" * 88)
    print(f"平均端到端（说完到出声）: {sum(tot)/len(tot):.2f}s   （n={len(tot)}，未计页面缓冲）")
