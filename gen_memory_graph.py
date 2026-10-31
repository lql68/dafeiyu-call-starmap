"""把 livingmemory 的真实知识图谱导成识海球能画的数据。

输出 D:\\deepseek harness\\ai-live\\memory-graph.json
  meta  : 真实计数（节点/边/原子/文档）+ 导出时间
  nodes : [type, degree, age_days, weight, value]   —— 球面坐标由前端算
  links : [a, b, weight]                            —— 索引指向 nodes

布点思路：先用 Fibonacci 球面均匀撒点，再沿着真实边做几轮「弹簧 + 回归球面」，
这样互相有关系的记忆会自然聚成团，而不是随机均匀的一片。
"""

import json
import math
import os
import sqlite3
import time

DB = r"D:\deepseek harness\astrbot-lab\AstrBot\data\plugin_data\astrbot_plugin_livingmemory\livingmemory.db"
OUT = r"D:\deepseek harness\ai-live\memory-graph.json"

MAX_NODES = 900          # 球上最多画这么多（多了线看不清）
MIN_DEGREE = 1
RELAX_ROUNDS = 6
SPRING = 0.06
TO_SPHERE = 0.22

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

meta = {
    "nodes_all": con.execute("select count(*) from graph_nodes").fetchone()[0],
    "atoms_active": con.execute(
        "select count(*) from memory_atoms where status = 'active'").fetchone()[0],
    "avg_importance": round(con.execute(
        "select avg(importance) from memory_atoms").fetchone()[0] or 0.0, 3),
    "edges_all": con.execute("select count(*) from graph_edges").fetchone()[0],
    "atoms_all": con.execute("select count(*) from memory_atoms").fetchone()[0],
    "docs_all": con.execute("select count(*) from documents").fetchone()[0],
    "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}

# ── 1. 节点与度数 ────────────────────────────────────────────
raw_nodes = con.execute(
    "select id, node_type, node_value, created_at from graph_nodes"
).fetchall()

edge_rows = con.execute(
    "select source_node_id as s, target_node_id as t, weight, confidence, relation_type"
    " from graph_edges where status is null or status = 'active'"
).fetchall()

deg = {}
for e in edge_rows:
    deg[e["s"]] = deg.get(e["s"], 0) + 1
    deg[e["t"]] = deg.get(e["t"], 0) + 1

# 每个节点关联到的原子的平均 importance（用来分「恒星 / 星云 / 尘埃」）
imp = {}
for r in con.execute(
    """
    SELECT gn.id AS nid, AVG(ma.importance) AS imp
    FROM graph_nodes gn
    JOIN graph_edges ge ON ge.source_node_id = gn.id
    JOIN memory_atoms ma ON ma.parent_memory_id = ge.source_memory_id
    GROUP BY gn.id
    """
):
    imp[r["nid"]] = float(r["imp"] or 0.0)

now = time.time()


def age_days(s):
    """created_at 是 ISO 字符串，算成「距今多少天」。"""
    if not s:
        return 999.0
    try:
        t = time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
        return max(0.0, (now - t) / 86400.0)
    except Exception:
        return 999.0


# 挑度数高的节点（它们才有结构信息）
cand = [n for n in raw_nodes if deg.get(n["id"], 0) >= MIN_DEGREE]
cand.sort(key=lambda n: deg.get(n["id"], 0), reverse=True)
cand = cand[:MAX_NODES]

keep = {n["id"]: i for i, n in enumerate(cand)}

TYPES = ["topic", "fact", "entity", "event", "person", "preference", "other"]

# ── 语义类别（前端按 c 上色）────────────────────────────────
# 0 人物 / 1 技能 / 2 情绪 / 3 约定计划 / 4 爱好 / 5 习惯 / 6 其他
CATS = ["人物", "技能", "情绪", "约定计划", "爱好", "习惯", "其他"]

CAT_RULES = [
    (1, ["报错", "token", "模型", "部署", "显存", "脚本", "api", "上下文", "超时",
         "服务器", "代码", "命令行", "安装", "配置", "接口", "日志", "进程", "端口",
         "权重", "推理", "训练", "提示词", "prompt", "gpu", "显卡", "内存", "数据库",
         "插件", "爬虫", "反代", "webui", "docker", "python", "node", "git"]),
    (2, ["担心", "害怕", "喜欢", "讨厌", "生气", "委屈", "开心", "难过", "累",
         "烦", "急", "哭", "舍不得", "心疼", "孤独", "焦虑", "安心", "吃醋",
         "想念", "不想", "愿意", "无奈", "感动", "高兴", "伤心", "紧张"]),
    (3, ["说好", "答应", "明天", "等下", "记得", "等我", "回来", "约好", "回头",
         "晚点", "待会", "提醒", "别忘了", "下次", "先说", "等会", "一会儿", "改天"]),
    (4, ["吃", "玩", "看", "听", "喝", "抖音", "b站", "游戏", "音乐", "动漫",
         "电影", "零食", "饭", "奶茶", "咖啡", "唱歌", "拍照", "追番", "番剧"]),
    (5, ["每天", "总是", "经常", "一直", "老是", "习惯", "照例", "每次", "又",
         "天天", "从来", "向来"]),
]


def classify(node_type, value):
    if node_type == "person":
        return 0
    v = (value or "").lower()
    for idx, kws in CAT_RULES:
        for kw in kws:
            if kw in v:
                return idx
    return 6
maxd = max((deg.get(n["id"], 0) for n in cand), default=1) or 1
nodes = []
for n in cand:
    tidx = TYPES.index(n["node_type"]) if n["node_type"] in TYPES else len(TYPES) - 1
    value = (n["node_value"] or "").strip().replace("\n", " ")
    if len(value) > 34:
        value = value[:33] + "…"
    d = deg.get(n["id"], 0)
    # 度数越高越靠球心，外围是只有一两条边的零散记忆 —— 一眼能看出"核心/边缘"
    rad = round(1.0 - 0.40 * (math.log2(1 + d) / math.log2(1 + maxd)), 3)
    cat = classify(n["node_type"], value)
    nodes.append({
        "t": tidx,
        "c": cat,
        "k": n["node_type"],
        "imp": round(imp.get(n["id"], 0.0), 3),
        "d": d,
        "a": round(age_days(n["created_at"]), 1),
        "r": rad,
        "v": value,
    })

links = []
for e in edge_rows:
    a, b = keep.get(e["s"]), keep.get(e["t"])
    if a is None or b is None or a == b:
        continue
    w = float(e["weight"] or 1.0) * float(e["confidence"] or 1.0)
    if w < 0.40:            # 太弱的连线不画，否则一团毛球什么也看不出
        continue
    links.append([a, b, round(min(1.0, w), 3)])

# ── 2. 布点：Fibonacci 球面 + 沿边松弛 ───────────────────────
N = len(nodes)
GA = math.pi * (3.0 - math.sqrt(5.0))
pos = []
for i in range(N):
    y = 1.0 - (i / max(1, N - 1)) * 2.0
    r = math.sqrt(max(0.0, 1.0 - y * y))
    th = GA * i
    pos.append([math.cos(th) * r, y, math.sin(th) * r])

for _ in range(RELAX_ROUNDS):
    # 弹簧：有边就互相拉近
    for a, b, w in links:
        pa, pb = pos[a], pos[b]
        dx, dy, dz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        k = SPRING * (0.4 + 0.6 * w)
        pa[0] += dx * k; pa[1] += dy * k; pa[2] += dz * k
        pb[0] -= dx * k; pb[1] -= dy * k; pb[2] -= dz * k
    # 回归球面：每点归一化，保证还是个球
    for p in pos:
        L = math.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]) or 1.0
        tx, ty, tz = p[0] / L, p[1] / L, p[2] / L
        p[0] += (tx - p[0]) * TO_SPHERE
        p[1] += (ty - p[1]) * TO_SPHERE
        p[2] += (tz - p[2]) * TO_SPHERE

for i, p in enumerate(pos):
    L = math.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]) or 1.0
    rad = nodes[i]["r"]
    nodes[i]["x"] = round(p[0] / L * rad, 4)
    nodes[i]["y"] = round(p[1] / L * rad, 4)
    nodes[i]["z"] = round(p[2] / L * rad, 4)

meta["nodes_shown"] = N
meta["links_shown"] = len(links)
meta["max_degree"] = max((n["d"] for n in nodes), default=0)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"meta": meta, "nodes": nodes, "links": links}, f,
              ensure_ascii=False, separators=(",", ":"))

print("导出 ->", OUT)
print("  ", os.path.getsize(OUT) // 1024, "KB")
print("   节点", N, "/", meta["nodes_all"], "  边", len(links), "/", meta["edges_all"])
print("   原子", meta["atoms_all"], "  文档", meta["docs_all"], "  最大度数", meta["max_degree"])
cnt = {}
for nd in nodes:
    cnt[CATS[nd["c"]]] = cnt.get(CATS[nd["c"]], 0) + 1
print("   类别:", "  ".join(f"{k} {v}" for k, v in
      sorted(cnt.items(), key=lambda kv: -kv[1])))
