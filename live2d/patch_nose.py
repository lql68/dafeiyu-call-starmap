# -*- coding: utf-8 -*-
"""盖掉模型自带的那个黑色小图标 + 补上授权要求的署名。

黑块位置（相对 .l2d-wrap）：中心约 50% / 38%，大小约 2.7% x 4.2%。
她说话时嘴在 42% 以下，所以这块补丁不会挡嘴。
"""
import io

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()

if "nose-patch" in s:
    print("already")
else:
    css_anchor = "  #l2dCanvas{display:block}"
    css_new = (
        "  #l2dCanvas{display:block}\n"
        "  /* 模型自带的黑图标贴在鼻梁上，图层又被 pixi 内部缓存挡住改不动，\n"
        "     用一块和她肤色一样的柔边补丁盖住；位置固定在头像里，跟着容器一起缩放。 */\n"
        "  .nose-patch{position:absolute;left:50%;top:38%;width:2.9%;height:4.4%;\n"
        "    transform:translate(-50%,-50%);pointer-events:none;border-radius:50%;\n"
        "    background:radial-gradient(ellipse at 50% 50%, #fcece5 0 52%, #fae7df 72%, rgba(250,231,223,0) 100%);\n"
        "    filter:blur(1.1px);z-index:2}"
    )
    assert css_anchor in s, "css anchor missing"
    s = s.replace(css_anchor, css_new, 1)

    html_anchor = '<canvas id="l2dCanvas"></canvas>'
    html_new = ('<canvas id="l2dCanvas"></canvas>\n'
                '        <div class="nose-patch"></div>')
    assert html_anchor in s, "canvas anchor missing"
    s = s.replace(html_anchor, html_new, 1)

    # 署名（模型授权要求，公开使用必须写）
    credit_anchor = 'AI 生成内容 · 虚拟形象'
    credit_new = ('AI 生成内容 · 虚拟形象 · 模型 神宫凉子 / Live2D 霓虹猫_NeonNeko')
    if credit_anchor in s:
        s = s.replace(credit_anchor, credit_new, 1)
        print("credit updated")
    else:
        print("credit anchor missing, skipped")

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("patched")
