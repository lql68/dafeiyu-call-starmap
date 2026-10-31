# -*- coding: utf-8 -*-
"""VTube Studio API 桥。

VTS 的 API 是 WebSocket + JSON，端口 8001（设置里 Config_StartAPI 已打开）。
第一次连会弹窗问「允许 ai-live 控制模型吗」，点了才会给 token，token 存到
ai-live\\vts_token.json，之后不用再点。

对外只暴露三个动作：inject（写参数）、expression（表情开关）、hotkey（触发动作）。
全部走一个后台线程 + 队列，调用方永远不会阻塞。
"""
import json
import os
import queue
import threading
import time
import uuid

import websocket  # websocket-client

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "vts_token.json")
WS_URL = "ws://127.0.0.1:8001"
PLUGIN = "ai-live-avatar"
DEVELOPER = "dsh"


class VTS:
    def __init__(self, url=WS_URL, plugin=PLUGIN, developer=DEVELOPER):
        self.url = url
        self.plugin = plugin
        self.developer = developer
        self.token = self._load_token()
        self.ws = None
        self._q = queue.Queue(maxsize=4000)
        self._alive = False
        self._authed = False
        self._stop = False
        self.last_error = ""
        self.pending = {}
        self._t = threading.Thread(target=self._run, daemon=True, name="vts")

    # ---------- 外部接口 ----------
    def start(self):
        if not self._t.is_alive():
            self._t.start()
        return self

    @property
    def ready(self):
        return self._alive and self._authed

    def status(self):
        return {
            "alive": self._alive,
            "authed": self._authed,
            "has_token": bool(self.token),
            "error": self.last_error,
        }

    def inject(self, params, face_found=False, mode="set"):
        """params: {"ParamMouthOpenY": 0.5, ...}  —— 直接写值，不排队阻塞。"""
        msg = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": uuid.uuid4().hex,
            "messageType": "InjectParameterDataRequest",
            "data": {
                "faceFound": bool(face_found),
                "mode": mode,
                "parameterValues": [{"id": k, "value": float(v), "weight": 1.0}
                                    for k, v in params.items()],
            },
        }
        self._put(msg)

    def expression(self, name, active=True, fade=0.35):
        self._put({
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": uuid.uuid4().hex,
            "messageType": "ExpressionActivationRequest",
            "data": {"expressionFile": name, "active": bool(active), "fadeTime": fade},
        })

    def hotkey(self, hotkey_id):
        self._put({
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": uuid.uuid4().hex,
            "messageType": "HotkeyTriggerRequest",
            "data": {"hotkeyID": hotkey_id},
        })

    def stop(self):
        self._stop = True
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    # ---------- 内部 ----------
    def _put(self, msg):
        if not self.ready:
            return
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            # 塞爆了就把旧的丢掉一半（口型帧不值钱）
            for _ in range(200):
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            try:
                self._q.put_nowait(msg)
            except queue.Full:
                pass

    def _load_token(self):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("token") or None
        except Exception:
            return None

    def _save_token(self, tok):
        self.token = tok
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": tok, "plugin": self.plugin, "saved": time.time()}, f)
        except Exception:
            pass

    def _send(self, msg):
        self.ws.send(json.dumps(msg, ensure_ascii=False))

    def _req(self, mtype, data=None):
        rid = uuid.uuid4().hex
        m = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
             "requestID": rid, "messageType": mtype}
        if data is not None:
            m["data"] = data
        self._send(m)
        return rid

    def _handshake(self):
        self._req("APIStateRequest")
        if self.token:
            rid = self._req("AuthenticationRequest", {
                "pluginName": self.plugin, "pluginDeveloper": self.developer,
                "authenticationToken": self.token,
            })
            t0 = time.time()
            while time.time() - t0 < 8:
                try:
                    r = json.loads(self.ws.recv())
                except Exception:
                    break
                if r.get("messageType") == "AuthenticationResponse":
                    d = r.get("data") or {}
                    if d.get("authenticated"):
                        self._authed = True
                        return True
                    self.last_error = "token 被拒（VTS 里删过插件？）"
                    return False
            self.last_error = "认证超时"
            return False
        # 没 token：请求授权，VTS 会弹窗，等人点「允许」
        self._req("AuthenticationTokenRequest", {
            "pluginName": self.plugin, "pluginDeveloper": self.developer,
            "pluginIcon": None,
        })
        self.last_error = "等待在 VTube Studio 弹窗里点「允许」"
        self.ws.settimeout(None)
        while not self._stop:
            r = json.loads(self.ws.recv())          # 阻塞，等到人点为止
            if r.get("messageType") == "AuthenticationTokenResponse":
                d = r.get("data") or {}
                tok = d.get("authenticationToken")
                if tok:
                    self._save_token(tok)
                    self._authed = True
                    self.last_error = ""
                    return True
                self.last_error = "用户拒绝了授权"
                return False
        return False

    def _run(self):
        while not self._stop:
            try:
                self.ws = websocket.create_connection(self.url, timeout=6,
                                                      enable_multithread=True)
                self._alive = True
                self._authed = False
                if not self._handshake():
                    self._alive = False
                    time.sleep(5)
                    continue
                self.last_error = ""
                self.ws.settimeout(0.05)
                while not self._stop:
                    # 1) 读（顺带把排队消息的响应吞掉）
                    try:
                        raw = self.ws.recv()
                        if raw:
                            r = json.loads(raw)
                            if r.get("messageType") == "APIError":
                                self.last_error = (r.get("data") or {}).get("message", "APIError")
                    except Exception:
                        pass
                    # 2) 写
                    sent = 0
                    while sent < 40:
                        try:
                            msg = self._q.get_nowait()
                        except queue.Empty:
                            break
                        self._send(msg)
                        sent += 1
                    if sent == 0:
                        time.sleep(0.016)          # ~60Hz 上限，别空转烧 CPU
            except Exception as e:
                self._alive = False
                self._authed = False
                self.last_error = "%s: %s" % (type(e).__name__, e)
                time.sleep(4)


def _setup_cli():
    """等授权 → 加载大肥鱼 → 口型扫一遍，全程写 vts_bridge.log。"""
    import sys

    log = open(os.path.join(HERE, "vts_bridge.log"), "a", encoding="utf-8", buffering=1)

    def p(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        log.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), s))

    v = VTS().start()
    p("等 VTS 授权（弹窗里点「允许」）…")
    for i in range(300):                       # 最多等 15 分钟
        time.sleep(1)
        st = v.status()
        if st["authed"]:
            p("已授权", st)
            break
        if i % 20 == 0 and i:
            p("还在等…", st)
    if not v.ready:
        p("超时，没授权", v.status())
        return 1

    v._put({"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": uuid.uuid4().hex, "messageType": "ModelLoadRequest",
            "data": {"model": "大肥鱼.model3.json"}})
    time.sleep(3)
    p("试写口型：6 秒，开合 3 次")
    import math
    for k in range(180):
        v.inject({"ParamMouthOpenY": 0.55 + 0.42 * math.sin(k / 9.0)})
        time.sleep(1 / 30)
    v.inject({"ParamMouthOpenY": 0.0})
    p("done，保持连接 60 秒方便观察")
    time.sleep(60)
    return 0


if __name__ == "__main__":
    import sys
    if "--setup" in sys.argv:
        sys.exit(_setup_cli())
    v = VTS().start()
    print("连上没:", v.status(), flush=True)
    for i in range(30):
        time.sleep(1)
        st = v.status()
        if st["authed"]:
            print("已授权", st, flush=True)
            break
        if i % 5 == 0:
            print("等授权…", st, flush=True)
    if v.ready:
        print("试写口型（3 秒开合 3 次）", flush=True)
        for k in range(90):
            v.inject({"ParamMouthOpenY": 0.5 + 0.45 * __import__("math").sin(k / 4.0)})
            time.sleep(1 / 30)
        v.inject({"ParamMouthOpenY": 0.0})
        print("done")
    else:
        print("没授权，放弃:", v.status())
    sys.exit(0)
