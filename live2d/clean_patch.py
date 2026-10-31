# -*- coding: utf-8 -*-
"""清掉上一轮留下的残渣：字面量 `r`n 和那个已经放弃的补丁 div。"""
import io
import re

P = r"D:\deepseek harness\ai-live\live.html"
s = io.open(P, encoding="utf-8").read()

before = s
s = s.replace('`r`n', '\n')                       # 字面量换行符
s = s.replace('<div class="nose-patch"></div>', '')
s = re.sub(r"\.nose-patch\{[^}]*\}\s*", "", s)    # 删掉没用的 CSS
io.open(P, "w", encoding="utf-8", newline="").write(s)

print("changed:", before != s)
print("nose-patch 残留:", s.count("nose-patch"))
print("`r`n 残留:", s.count("`r`n"))
