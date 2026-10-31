# -*- coding: utf-8 -*-
"""模拟 AstrBot 的调用：读 API 工作流，把 texts[] 注入 Simple String，POST /prompt，等结果。"""
import json
import sys
import time
import urllib.request

SRV = "http://127.0.0.1:8188"
WF = sys.argv[1]
TEXT = sys.argv[2]


def post(path, obj):
    req = urllib.request.Request(
        SRV + path,
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def get(path):
    return json.loads(urllib.request.urlopen(SRV + path, timeout=30).read())


wf = json.load(open(WF, encoding="utf-8"))

# —— 这一段就是 workflow_engine._update_text_nodes 的等价实现 ——
n = 0
for nid, node in wf.items():
    if node.get("class_type") != "Simple String":
        continue
    for key in ("text", "string"):
        if key in node.get("inputs", {}):
            node["inputs"][key] = TEXT
            n += 1
            break
print(f"注入 {n} 个 Simple String 节点")

client_id = "astrbot-test-0001"
r = post("/prompt", {"prompt": wf, "client_id": client_id})
pid = r["prompt_id"]
print("prompt_id:", pid, "| queued:", r.get("number"))
if r.get("node_errors"):
    print("node_errors:", json.dumps(r["node_errors"], ensure_ascii=False)[:600])

t0 = time.time()
while time.time() - t0 < 300:
    h = get(f"/history/{pid}")
    if pid in h:
        item = h[pid]
        st = item.get("status", {})
        print(f"完成，用时 {time.time()-t0:.1f}s，status={st.get('status_str')}")
        if st.get("status_str") == "error":
            for m in st.get("messages", []):
                if m[0] == "execution_error":
                    print("  错误节点:", m[1].get("node_type"), "|", m[1].get("exception_message", "")[:300])
        for nid, out in (item.get("outputs") or {}).items():
            for img in out.get("images", []):
                print(f"  输出 #{nid}: {img.get('filename')} (subfolder={img.get('subfolder','')}, type={img.get('type')})")
        sys.exit(0 if st.get("status_str") != "error" else 1)
    time.sleep(2)
print("超时")
sys.exit(2)
