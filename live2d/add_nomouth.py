# -*- coding: utf-8 -*-
"""给口型参数加 ?nomouth=1 开关，并打印参数量程，用来判断黑块是不是嘴参数造成的。"""
import io

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()

if "NO_MOUTH" in s:
    print("already")
else:
    s = s.replace(
        "const HIDE_PARTS = ['Part19', 'Part26', 'Part74'];",
        "const NO_MOUTH = /nomouth/.test(location.search);   // 排查：完全不动嘴参数\n"
        "const HIDE_PARTS = ['Part19', 'Part26', 'Part74'];",
        1)
    old = ("  set('ParamMouthOpenY', mouthP);\n"
           "  set('ParamMouthForm', 1 - mouthP * 0.6);       // 张嘴时嘴角收一点，像在说话")
    new = ("  if(!NO_MOUTH){\n"
           "    set('ParamMouthOpenY', mouthP);\n"
           "    set('ParamMouthForm', 1 - mouthP * 0.6);      // 张嘴时嘴角收一点，像在说话\n"
           "  }")
    assert old in s, "mouth anchor missing"
    s = s.replace(old, new, 1)
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("patched")
