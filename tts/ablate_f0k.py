import os, sys
sys.path.insert(0, r"D:\deepseek harness\ai-live\tts")
import numpy as np, soundfile as sf, json
from clone_v12 import loadw, to24, proc, SRC, OUT
y, sr = loadw(SRC)
rows=[]
CFG=[("d_f0k1.00", dict(target=4.1, f0k=1.00, n_dips=14, dip_db=-11, dip_w=55, pause_ms=70)),
     ("e_f0k0.85", dict(target=4.1, f0k=0.85, n_dips=14, dip_db=-11, dip_w=55, pause_ms=70)),
     ("f_f0k1.00_t5.0", dict(target=5.0, f0k=1.00, n_dips=12, dip_db=-9, dip_w=50, pause_ms=60)),
     ("g_f0k1.00_t3.6", dict(target=3.6, f0k=1.00, n_dips=18, dip_db=-13, dip_w=62, pause_ms=85))]
for tag,kw in CFG:
    o=proc(y,sr,**kw)
    raw=os.path.join(OUT,f"_r12_{tag}.wav"); sf.write(raw,o,sr)
    dst=to24(raw, os.path.join(OUT,f"v12_{tag}.wav"))
    import wave
    with wave.open(dst) as w: d=w.getnframes()/w.getframerate()
    rows.append(dict(name=tag,dur=round(d,2)))
    print(f"[gen] v12_{tag}  {d:.2f}s", flush=True)
