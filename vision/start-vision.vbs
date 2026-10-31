' 鲸鱼娘的眼睛和耳朵 —— 后台常驻（无窗口，每 4 秒存一张快照给通话窗用）
Option Explicit
Dim sh, py, script
Set sh = CreateObject("WScript.Shell")
py = "D:\sakana-py\pythonw.exe"
script = "D:\deepseek harness\ai-live\vision\vision.py"
sh.CurrentDirectory = "D:\deepseek harness\ai-live\vision"
sh.Run """" & py & """ """ & script & """ --snap-every 4", 0, False