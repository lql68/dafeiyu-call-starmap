# 生成脱敏的示例图谱，并把它内联进 starmap.html
#   · 保留 t/d/a/r/x/y/z/k/imp —— 所以星图的形状、层次、类别分布完全一样
#   · 把 v(实体名) / s(关联原文) / ms(记忆正文) 换成占位内容
#   · 本地运行时 starmap 会先 fetch 真的 memory-graph.json，所以你自己看到的还是真数据；
#     GitHub 上没有那个文件，它回落到内联的这份示例
import io
import json
import os
import re

ROOT = r"D:\deepseek harness\ai-live"
SRC = os.path.join(ROOT, "memory-graph.json")
HTML = os.path.join(ROOT, "starmap.html")
OUT = os.path.join(ROOT, "memory-graph.sample.json")

FAKE_ENTITY = [
    "北极星", "青柠", "第七张便签", "旧收音机", "百叶窗", "深夜便利店",
    "浅蓝毛线帽", "阁楼", "周四的雨", "车站长椅", "半杯冷咖啡", "窗台仙人掌",
    "末班车", "铅灰云", "书脊裂缝", "薄荷糖", "楼下猫", "白噪声",
]
FAKE_MEM = [
    "有人在半夜说起想吃点什么，最后只是喝了口水。",
    "那天的天气被人反复提起，说了三遍才停。",
    "她说要早点睡，然后继续聊了两个小时。",
    "被问到一个很久以前的问题，答得含含糊糊。",
    "有人抱怨屋子太冷，但没有去关窗。",
    "聊到一半突然安静下来，谁都没先开口。",
    "记不清是谁先说了那句话，只记得说完都笑了。",
    "某个人提到自己今天走了很多路，脚有点酸。",
    "聊起一件没做完的事，说改天再说。",
    "有人把同一句话换了个说法又讲了一遍。",
    "说了句「没什么」，然后换了个话题。",
    "提到了一个名字，随后又绕开了。",
]


def fake_of(name):
    h = 0
    for ch in str(name):
        h = (h * 131 + ord(ch)) & 0xFFFFFF
    return FAKE_ENTITY[h % len(FAKE_ENTITY)]


d = json.load(io.open(SRC, encoding="utf-8"))
n_nodes = len(d.get("nodes") or [])

for i, nd in enumerate(d.get("nodes") or []):
    if "v" in nd:
        nd["v"] = fake_of(nd["v"]) + ("·%d" % (i % 97) if i % 7 == 0 else "")
    if "s" in nd:
        nd["s"] = FAKE_MEM[i % len(FAKE_MEM)]
    if "ms" in nd and nd["ms"]:
        nd["ms"] = [FAKE_MEM[(i + k) % len(FAKE_MEM)] for k in range(len(nd["ms"]))]

io.open(OUT, "w", encoding="utf-8").write(
    json.dumps(d, ensure_ascii=False, separators=(",", ":"))
)
print("示例图谱:", os.path.getsize(OUT), "字节,", n_nodes, "个节点（文本已全部替换）")

# ── 内联进 starmap.html ───────────────────────────────────────
s = io.open(HTML, encoding="utf-8").read()
m = re.search(r"window\.__GRAPH__\s*=\s*", s)
if not m:
    m = re.search(r"window\.__GRAPH__\s*=\s*", s)
assert m, "找不到 window.__GRAPH__ 赋值"
beg = m.end()
end = s.find(";\n", beg)
assert end > beg, "找不到内联数据的结尾"

payload = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
s = s[:beg] + payload + s[end:]
io.open(HTML, "w", encoding="utf-8", newline="").write(s)
print("已内联进 starmap.html，文件共", len(s.encode("utf-8")), "字节")
