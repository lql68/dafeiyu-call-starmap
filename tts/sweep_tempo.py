import os, sys, json
sys.path.insert(0, r"D:\deepseek harness\ai-live\tts")
import importlib, clone_v13 as v
from clone_v13 import build, OUT
SRC = os.path.join(OUT, "v9_base_her.wav")
rows=[]
for t in (4.2, 3.8, 3.4, 3.0):
    rows.append(build(SRC, t, 1, -10, 55, 65, f"t{str(t).replace('.','p')}"))
print(json.dumps([r for r in rows if r], ensure_ascii=False, indent=1))
