# -*- coding: utf-8 -*-
"""给复制过来的大肥鱼模型补上 Motions / Expressions 声明。

原版 model3.json 只有 Moc/Textures/Physics/DisplayInfo —— 动作和表情文件是散落的，
VTube Studio 自己能扫到，但 pixi-live2d-display 只认 model3.json 里声明过的。
这里按目录内容生成一份新的 model3.json（只改这份副本，不动桌面原件）。
"""
import json
import os
import re

ROOT = r"D:\deepseek harness\ai-live\live2d\model\大肥鱼"
M3 = os.path.join(ROOT, "大肥鱼.model3.json")

with open(M3, encoding="utf-8") as f:
    m = json.load(f)

fr = m["FileReferences"]

# ---- 动作 ----
motions = {}
anim_dir = os.path.join(ROOT, "Animation")
for fn in sorted(os.listdir(anim_dir)):
    if not fn.endswith(".motion3.json"):
        continue
    name = fn[: -len(".motion3.json")]
    group = "Idle" if name.upper() == "IDLE" else "Tap"
    motions.setdefault(group, []).append(
        {"File": f"Animation/{fn}", "FadeInTime": 1.0, "FadeOutTime": 1.0}
    )
# 举手 / 竖手指 这几种切换动作单独归组，方便点名播
for group, pats in {
    "Hand": ["举手", "默认手", "狗尾草", "竖手指"],
}.items():
    picked = [x for x in motions.get("Tap", []) if any(p in x["File"] for p in pats)]
    if picked:
        motions.setdefault(group, []).extend(picked)
        motions["Tap"] = [x for x in motions.get("Tap", []) if x not in picked]

# ---- 表情 ----
exprs = []
exp_dir = os.path.join(ROOT, "Exp3")
for fn in sorted(os.listdir(exp_dir)):
    if not fn.endswith(".exp3.json"):
        continue
    name = fn[: -len(".exp3.json")]
    exprs.append({"Name": name, "File": f"Exp3/{fn}"})

fr["Motions"] = motions
fr["Expressions"] = exprs

# 嘴型参数交给代码驱动
m["Groups"] = [
    {"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeROpen", "ParamEyeLOpen"]},
    {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]},
]

with open(M3, "w", encoding="utf-8") as f:
    json.dump(m, f, ensure_ascii=False, indent="\t")

print("motions:", {k: len(v) for k, v in motions.items()})
print("expressions:", len(exprs), "->", [e["Name"] for e in exprs])
