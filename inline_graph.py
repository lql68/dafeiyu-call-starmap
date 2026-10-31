# 1) 把内联快照换成新 json（带 k / imp）；2) 底部换成四层图例
import io, json, re

HTML = r"D:\deepseek harness\ai-live\starmap.html"
JSON = r"D:\deepseek harness\ai-live\memory-graph.json"

s = io.open(HTML, encoding="utf-8").read()
g = json.load(io.open(JSON, encoding="utf-8"))

blob = json.dumps(g, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

i = s.find("window.__GRAPH__ = ")
assert i > 0, "找不到 __GRAPH__ 赋值"
j = s.find(";\n", i)
assert j > i, "找不到赋值结束"
old_len = j - i
s = s[:i] + "window.__GRAPH__ = " + blob + s[j:]

# 底部图例
old_foot = "拖动 = 转视角 · 空格 = 暂停自转 · 点节点 = 只看它和它认识的"
new_foot = (
    '<b style="color:#78b4ff">●</b> 黑洞 枢纽记忆　'
    '<b style="color:#fff1d6">●</b> 恒星 人 / 重要　'
    '<b style="color:#e8d4ae">●</b> 星云 话题　'
    '<b style="color:#94acc9">●</b> 尘埃 零散事实'
    '　　拖动 = 转视角 · 空格 = 暂停 · 点节点 = 只看它'
)
if old_foot in s:
    s = s.replace(old_foot, new_foot, 1)
    print("底部图例已换")
else:
    print("⚠ 底部文字没匹配上")

io.open(HTML, "w", encoding="utf-8", newline="").write(s)
print(f"内联快照 {old_len} -> {len(blob)} 字符；文件共 {len(s)} 字节")
print("k 分布:", {k: sum(1 for n in g["nodes"] if n.get("k") == k)
                  for k in ("person", "topic", "fact")})
