# -*- coding: utf-8 -*-
"""导出 livingmemory 全量记忆图谱，供「记忆星图」前端使用。

输出 memstarmap/data/graph.json：
  nodes[]  图谱节点（fact/topic/person），带度数、时间、以及关联 atom 的衰减状态
  edges[]  图谱边（source/target/relation/weight/confidence）
  atoms[]  全部 memory_atoms（含 ttl/expires/importance/decay_type/status）
  docs[]   documents 概要（不给全文，只给长度与时间）
  meta     统计
"""
import json
import os
import sqlite3
import time
import datetime
import math
from collections import defaultdict

D = r"D:\deepseek harness\astrbot-lab\AstrBot\data\plugin_data\astrbot_plugin_livingmemory"
DB = os.path.join(D, "livingmemory.db")
OUT_DIR = r"D:\deepseek harness\ai-live\memstarmap\data"
OUT = os.path.join(OUT_DIR, "graph.json")

os.makedirs(OUT_DIR, exist_ok=True)
now = time.time()

c = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
c.row_factory = sqlite3.Row
q = c.execute

# ── 节点 ────────────────────────────────────────────────
nodes = {}
for r in q("""SELECT id, node_key, node_type, node_value, canonical_value,
                     metadata, created_at, updated_at FROM graph_nodes"""):
    created = r["created_at"]
    if isinstance(created, str):
        try:
            created = datetime.datetime.fromisoformat(created).timestamp()
        except Exception:
            created = now
    nodes[r["id"]] = {
        "id": r["id"],
        "key": r["node_key"],
        "type": r["node_type"],
        "value": (r["node_value"] or "")[:200],
        "created": created,
        "age_days": round((now - created) / 86400.0, 2),
        "deg": 0,
    }

# ── 边 ──────────────────────────────────────────────────
edges = []
for r in q("""SELECT source_node_id s, target_node_id t, relation_type rel,
                     weight w, confidence cf FROM graph_edges"""):
    s, t = r["s"], r["t"]
    if s in nodes and t in nodes:
        edges.append({
            "s": s, "t": t, "rel": r["rel"],
            "w": round(float(r["w"] or 1.0), 3),
            "cf": round(float(r["cf"] or 0.5), 3),
        })
        nodes[s]["deg"] += 1
        nodes[t]["deg"] += 1

# ── 原子：挂到同名/同值的节点上，用来染色（新鲜度 / 快过期）────
atoms = []
sim_by_node = defaultdict(list)   # node id -> [importance...]
for r in q("""SELECT atom_type, content, importance, confidence, created_at,
                     last_accessed_at, ttl_days, expires_at, status,
                     reinforcement_count, decay_type, session_id
              FROM memory_atoms"""):
    ttl = float(r["ttl_days"] or 30.0)
    exp = float(r["expires_at"] or 0.0)
    age = max(0.0, (now - float(r["created_at"] or now)) / 86400.0)
    # 与插件一致的衰减评分（memory_atom.compute_decay_score）
    eff = max(1.0, ttl)
    if r["decay_type"] == "linear":
        score = max(0.0, 1.0 - age / eff)
    elif r["decay_type"] == "step":
        score = 1.0 if age <= eff else 0.05
    else:
        score = math.exp(-math.log(2) * age / max(0.5, eff / 2.0))
    atoms.append({
        "type": r["atom_type"],
        "text": (r["content"] or "")[:300],
        "imp": round(float(r["importance"] or 0.5), 3),
        "conf": round(float(r["confidence"] or 0.7), 3),
        "ttl": round(ttl, 1),
        "age_days": round(age, 2),
        "left_days": round((exp - now) / 86400.0, 1),
        "decay": round(score, 3),
        "status": r["status"],
        "decay_type": r["decay_type"],
        "reinf": r["reinforcement_count"],
        "session": r["session_id"],
    })

# 把 atom 的「最差衰减分」摊到节点上：节点里最长的那条文字包含 atom 文本时算命中
# （图谱节点和图谱 entry 之间没有直接外键，用文本前缀匹配，成本可接受）
atom_by_prefix = {}
for a in atoms:
    k = a["text"][:12]
    if len(k) >= 6:
        atom_by_prefix.setdefault(k, []).append(a)

for n in nodes.values():
    v = n["value"][:12]
    hit = atom_by_prefix.get(v)
    if hit:
        n["decay"] = min(x["decay"] for x in hit)
        n["imp"] = round(sum(x["imp"] for x in hit) / len(hit), 3)
        n["atoms"] = len(hit)
    else:
        # 没有原子信息的节点，按年龄给一个估计衰减
        n["decay"] = round(max(0.0, 1.0 - n["age_days"] / 180.0), 3)
        n["imp"] = 0.35
        n["atoms"] = 0

# ── documents 概要 ─────────────────────────────────────
docs = []
for r in q("""SELECT doc_id, LENGTH(text) ln, metadata, created_at
              FROM documents ORDER BY created_at DESC LIMIT 400"""):
    try:
        md = json.loads(r["metadata"] or "{}")
    except Exception:
        md = {}
    docs.append({
        "doc": r["doc_id"][:24] if r["doc_id"] else "",
        "len": r["ln"],
        "session": (md.get("session_id") or "")[:48],
        "created": r["created_at"],
    })

# ── 输出 ────────────────────────────────────────────────
data = {
    "meta": {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nodes": len(nodes),
        "edges": len(edges),
        "atoms": len(atoms),
        "docs": len(docs),
        "atoms_active": sum(1 for a in atoms if a["status"] == "active"),
        "atoms_expired": sum(1 for a in atoms if a["left_days"] < 0),
        "avg_importance": round(sum(a["imp"] for a in atoms) / max(1, len(atoms)), 3),
        "avg_decay": round(sum(a["decay"] for a in atoms) / max(1, len(atoms)), 3),
        "span_days": round((now - min(n["created"] for n in nodes.values())) / 86400.0, 1),
    },
    "nodes": list(nodes.values()),
    "edges": edges,
    "atoms": atoms,
    "docs": docs,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

print("已导出", OUT)
print("  %d KB" % (os.path.getsize(OUT) // 1024))
print("  nodes %d / edges %d / atoms %d" % (len(nodes), len(edges), len(atoms)))
print("  meta:", json.dumps(data["meta"], ensure_ascii=False))
