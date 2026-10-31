# -*- coding: utf-8 -*-
"""隐藏模型里自带的小道具 Part（按键/加载），它们本该由 VTS 表情关掉。"""
import io

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()

if "HIDE_PARTS" in s:
    print("already patched")
else:
    decl = "let mouthP = 0, emotionNow = '', emotionUntil = 0;"
    s = s.replace(
        decl,
        decl + "\n"
        "const HIDE_PARTS = ['Part19', 'Part26', 'Part74'];   // 按键 ×2、加载图标",
        1,
    )
    anchor = "  if(emotionNow && t > emotionUntil){"
    add = (
        "  /* 自带小道具（按键/加载图标）在 VTS 里默认是关的，网页里没人替她按掉，\n"
        "     会变成一个黑方块贴脸上。按 Part 名永久关掉。 */\n"
        "  for(const pid of HIDE_PARTS){ try{ l2dCore.setPartOpacityById(pid, 0); }catch(e){} }\n"
    )
    assert anchor in s, "anchor missing"
    s = s.replace(anchor, add + anchor, 1)
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("patched:", s.count("HIDE_PARTS"))
