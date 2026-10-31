# -*- coding: utf-8 -*-
"""把 ComfyUI 的 UI 格式工作流转成 API 格式，并把正面提示词换成 Simple String 节点。

AstrBot 的 comfyui 插件只认 API 格式，并且只替换 class_type == "Simple String"
且 inputs 里有 text/string 的节点。所以这里：
  1. 沿 KSampler 的 positive 连线找到正面 CLIPTextEncode
  2. 把它的 text 取值挪进一个新的 "100" 号 Simple String 节点
  3. CLIPTextEncode.text 改成 ["100", 0]
"""
import json
import os
import sys

WIDGETS = {
    "CheckpointLoaderSimple": ["ckpt_name"],
    "CLIPTextEncode": ["text"],
    "EmptyLatentImage": ["width", "height", "batch_size"],
    # KSampler 的 widgets_values 第 2 个是 control_after_generate，不是 input
    "KSampler": ["seed", None, "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "LatentUpscaleBy": ["upscale_method", "scale_by"],
    "VAEDecode": [],
    "SaveImage": ["filename_prefix"],
    "PreviewImage": [],
}


def convert(ui):
    nodes = {n["id"]: n for n in ui["nodes"]}
    # link_id -> [link_id, origin_id, origin_slot, target_id, target_slot, type]
    links = {l[0]: l for l in ui["links"]}

    api = {}
    for nid, n in nodes.items():
        ct = n["type"]
        if ct not in WIDGETS:
            print(f"  ! 跳过不认识的节点类型 {ct} (#{nid})")
            continue
        inputs = {}

        # 连线进来的输入
        for slot in n.get("inputs") or []:
            lid = slot.get("link")
            if lid is None or lid not in links:
                continue
            oid, oslot = links[lid][1], links[lid][2]  # [link_id, origin_id, origin_slot, ...]
            inputs[slot["name"]] = [str(oid), oslot]

        # widgets_values 按位置映射
        wv = n.get("widgets_values") or []
        names = WIDGETS[ct]
        idx = 0
        for name in names:
            if name is None:          # 占位：跳过这个 widget（如 control_after_generate）
                idx += 1
                continue
            if idx < len(wv) and name not in inputs:
                inputs[name] = wv[idx]
            idx += 1

        api[str(nid)] = {"class_type": ct, "inputs": inputs}

    return api


def find_positive(api, ui):
    """沿 KSampler.positive 找正面提示词节点。"""
    for nid, node in api.items():
        if node["class_type"] != "KSampler":
            continue
        pos = node["inputs"].get("positive")
        if isinstance(pos, list):
            src = pos[0]
            if api.get(src, {}).get("class_type") == "CLIPTextEncode":
                return src
    # 兜底：提示词里带 masterpiece / best quality 的那个
    for nid, node in api.items():
        if node["class_type"] == "CLIPTextEncode":
            t = str(node["inputs"].get("text", ""))
            if "masterpiece" in t or "best quality" in t:
                return nid
    return None


def main(src, dst, sid="100"):
    ui = json.load(open(src, encoding="utf-8"))
    api = convert(ui)
    pos = find_positive(api, ui)
    if pos is None:
        print("  ! 找不到正面提示词节点")
        return 1
    text = api[pos]["inputs"].pop("text", "")
    api[sid] = {"class_type": "Simple String", "inputs": {"text": text}}
    api[pos]["inputs"]["text"] = [sid, 0]

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(api, f, ensure_ascii=False, indent=2)

    print(f"  {os.path.basename(dst)}  {len(api)} 个节点，正面=#{pos}←SimpleString#{sid}")
    for nid, n in api.items():
        print(f"    #{nid:<4} {n['class_type']:<26} {json.dumps(n['inputs'], ensure_ascii=False)[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
