# -*- coding: utf-8 -*-
"""把参考音频换成「大肥鱼（机灵版）」，并关掉为旧（唱歌）参考调出来的变速补丁。

旧参考是一首歌的音色，节奏拖，所以要 atempo 1.39 把它拽回说话速度；
新的机灵版本身就是说语速（15 字 3.39 秒），再加速就飘了 —— 变速关到 1.0，停顿只留 40ms。
"""
import io

P = r"D:\deepseek harness\ai-live\voice_server.py"
s = io.open(P, encoding="utf-8").read()

pairs = [
    ('HER = os.path.join(REFD, "her_timbre_breathed.wav")',
     'HER = os.path.join(REFD, "jiling.wav")          # 大肥鱼（机灵版）：干净人声、说话语速'),
    ('"voice": "her_timbre_breathed"',
     '"voice": "jiling"'),
    ('FACTOR = 1.39          # 实测最优变速比（唱腔 1.11 -> 0.48~0.58）',
     'FACTOR = 1.0            # 旧唱歌参考才要 1.39；机灵版本身就是说语速，别再加速'),
    ('PAUSE_MS = 70',
     'PAUSE_MS = 40'),
]

for old, new in pairs:
    if old not in s:
        print("!! 没找到:", old[:50])
    else:
        s = s.replace(old, new, 1)
        print("ok:", old[:44])

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("HER 行:", [ln for ln in s.splitlines() if ln.startswith("HER =")])
print("FACTOR:", [ln for ln in s.splitlines() if ln.startswith("FACTOR")])
