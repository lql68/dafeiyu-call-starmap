# -*- coding: utf-8 -*-
"""给 voice_server 接上 VTube Studio：
   - 启动时起一个 VTS 桥（懒连接，连不上不影响别的功能）
   - GET  /api/vts/status         -> 桥的状态
   - POST /api/mouth {open,...}   -> 写 MouthOpen / MouthSmile（页面按音频振幅推）
   - POST /api/vts/expression {name, active} -> 表情开关
"""
import io

P = r"D:\deepseek harness\ai-live\voice_server.py"
s = io.open(P, encoding="utf-8").read()

# 1) 头部文档
s = s.replace(
    "    POST /api/hear  <wav>     -> {text, ms}           听清他说了什么",
    "    POST /api/hear  <wav>     -> {text, ms}           听清他说了什么\n"
    "    POST /api/mouth {open}    -> {ok}                 把口型推给 VTube Studio\n"
    "    POST /api/vts/expression {name, active} -> {ok}\n"
    "    GET  /api/vts/status      -> {alive, authed, error}",
    1)

# 2) import + 实例
anchor = 'STATE = {"ready": False, "state": "starting", "queue": 0, "voice": "jiling"}'
if anchor not in s:
    raise SystemExit("STATE 锚点没找到")
s = s.replace(anchor, anchor + '''

# ---- VTube Studio 桥（连不上就静默，不影响网页那条路）----
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from vts_bridge import VTS
    VTSB = VTS()
    if os.environ.get("AI_LIVE_VTS", "on").lower() not in ("off", "0", "no", "none"):
        VTSB.start()
except Exception as _e:                                    # pragma: no cover
    print("[vts] 桥没起来:", _e)
    VTSB = None

# 最近一次口型值：VTS 那边每秒要几十次，做个极轻的合并
_MOUTH = {"open": 0.0, "smile": 0.35, "ts": 0.0}
_MOUTH_LOCK = threading.Lock()''', 1)

# 3) do_GET 加 status
s = s.replace(
    '''        if u.path == "/api/status":
            return self._json({**STATE, "cache": len(_CACHE)})''',
    '''        if u.path == "/api/status":
            return self._json({**STATE, "cache": len(_CACHE),
                               "vts": VTSB.status() if VTSB else {"off": True}})
        if u.path == "/api/vts/status":
            return self._json(VTSB.status() if VTSB else {"off": True})''', 1)

# 4) do_POST 加 /api/mouth 和 /api/vts/expression
s = s.replace(
    '''        if u.path != "/api/say":
            return self._json({"error": "not found"}, 404)''',
    '''        # ---- 口型：页面按播放音频的振幅推过来 ----
        if u.path == "/api/mouth":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            op = max(0.0, min(1.0, float(payload.get("open") or 0.0)))
            sm = payload.get("smile")
            with _MOUTH_LOCK:
                _MOUTH["open"] = op
                if sm is not None:
                    _MOUTH["smile"] = max(0.0, min(1.0, float(sm)))
                _MOUTH["ts"] = time.time()
            if VTSB and VTSB.ready:
                VTSB.inject({"MouthOpen": op, "MouthSmile": _MOUTH["smile"]})
            return self._json({"ok": True, "vts": bool(VTSB and VTSB.ready)})

        # ---- 表情 ----
        if u.path == "/api/vts/expression":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json({"error": "bad json"}, 400)
            name = (payload.get("name") or "").strip()
            if not name:
                return self._json({"error": "empty name"}, 400)
            if VTSB and VTSB.ready:
                VTSB.expression(name, bool(payload.get("active", True)),
                                float(payload.get("fade", 0.35)))
            return self._json({"ok": bool(VTSB and VTSB.ready), "name": name})

        if u.path != "/api/say":
            return self._json({"error": "not found"}, 404)''', 1)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("voice_server 已接上 VTS")
for key in ("/api/mouth", "/api/vts/expression", "/api/vts/status", "from vts_bridge import VTS"):
    print("  ", key, "->", s.count(key))
