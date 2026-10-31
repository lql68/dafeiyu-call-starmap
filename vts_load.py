# -*- coding: utf-8 -*-
"""等 VTS 里出现一个已加载的模型 → 换成大肥鱼 → 验口型。

VTS 在「没有任何模型」的状态下，界面上那个图标面板会一直开着，
ModelLoadRequest 永远返回 errorID 154（Cannot currently unload model）。
所以这里只做两件事：等、然后验。断线就重连（VTS 会主动踢掉连着报错的客户端）。
"""
import json
import math
import time
import uuid

import websocket

URL = "ws://127.0.0.1:8001"
TOKEN = json.load(open(r"D:\deepseek harness\ai-live\vts_token.json", encoding="utf-8"))["token"]
LOG = open(r"D:\deepseek harness\ai-live\vts_load.log", "a", encoding="utf-8", buffering=1)
DEADLINE = time.time() + 60 * 30          # 最多守 30 分钟


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), s))


def connect():
    ws = websocket.create_connection(URL, timeout=10)
    req(ws, "AuthenticationRequest", {"pluginName": "ai-live-avatar",
                                     "pluginDeveloper": "dsh", "authenticationToken": TOKEN})
    return ws


def req(ws, mt, data=None):
    m = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
         "requestID": uuid.uuid4().hex, "messageType": mt}
    if data is not None:
        m["data"] = data
    ws.send(json.dumps(m))
    exp = mt.replace("Request", "Response")
    while True:
        raw = ws.recv()
        if isinstance(raw, bytes):
            continue                      # VTS 会广播二进制帧，跳过
        try:
            r = json.loads(raw)
        except Exception:
            continue                      # 非 JSON 的广播帧也跳过
        if r.get("messageType") in (exp, "APIError"):
            return r


def main():
    ws = None
    loaded = None
    while time.time() < DEADLINE:
        try:
            if ws is None:
                ws = connect()
                p("已连上 VTS")
            cur = req(ws, "CurrentModelRequest")["data"]
            if cur.get("modelLoaded"):
                loaded = cur.get("modelName")
                p("VTS 里有模型了:", loaded)
                break
            if loaded is None:
                r = req(ws, "ModelLoadRequest", {"model": "大肥鱼"})
                # 注意：VTS 在「一个模型都没有」的状态下会假成功（modelID 为空、
                # 实际什么都没加载）。所以只认 CurrentModelRequest 的结果。
                if r.get("messageType") == "ModelLoadResponse":
                    time.sleep(2)
                    c2 = req(ws, "CurrentModelRequest")["data"]
                    if c2.get("modelLoaded"):
                        loaded = c2.get("modelName")
                        p("模型加载成功:", loaded)
                        break
                if not hasattr(main, "_said"):
                    p("VTS 还没有模型，等你在界面里点一个（点完我自动接手）")
                    main._said = True
            time.sleep(3)
        except SystemExit:
            raise
        except Exception as e:
            p("连接断了，重连:", type(e).__name__)
            try:
                ws.close()
            except Exception:
                pass
            ws = None
            time.sleep(3)

    if not loaded:
        p("等超时了，放弃")
        return 1

    # 换成大肥鱼（如果点到的是别的模型，这一步会成功，因为已经有模型可以 unloading）
    try:
        ws = ws or connect()
        cur = req(ws, "CurrentModelRequest")["data"]
        if not str(cur.get("modelName", "")).startswith("大肥鱼"):
            r = req(ws, "ModelLoadRequest", {"model": "大肥鱼"})
            p("换模型:", r.get("messageType"), r.get("data"))
            time.sleep(6)
        cur = req(ws, "CurrentModelRequest")["data"]
        p("当前模型:", cur.get("modelName"))

        prm = req(ws, "InputParameterListRequest").get("data", {})
        ids = [x.get("name") for x in prm.get("defaultParameters", [])]
        p("输入参数 %d 个, MouthOpen=%s" % (len(ids), "MouthOpen" in ids))

        p("口型扫 6 秒（看 VTS 里她的嘴）")
        for k in range(180):
            req(ws, "InjectParameterDataRequest", {
                "faceFound": False, "mode": "set",
                "parameterValues": [{"id": "MouthOpen",
                                     "value": 0.55 + 0.42 * math.sin(k / 9.0), "weight": 1.0}]})
            time.sleep(1 / 30)
        req(ws, "InjectParameterDataRequest", {"faceFound": False, "mode": "set",
                                              "parameterValues": [{"id": "MouthOpen",
                                                                   "value": 0.0, "weight": 1.0}]})
        p("口型 done —— 如果她刚才在说话，说明整条链路通了")

        p("试表情：脸红")
        req(ws, "ExpressionActivationRequest", {"expressionFile": "脸红.exp3.json",
                                               "active": True, "fadeTime": 0.3})
        time.sleep(3)
        req(ws, "ExpressionActivationRequest", {"expressionFile": "脸红.exp3.json",
                                               "active": False, "fadeTime": 0.3})
        p("表情 done")
    except Exception as e:
        p("验证阶段出错:", type(e).__name__, e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
