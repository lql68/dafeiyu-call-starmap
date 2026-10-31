# -*- coding: utf-8 -*-
"""VTS 授权后的自检：当前模型 → 加载大肥鱼 → 参数回读 → 口型扫一遍。"""
import json
import math
import time
import uuid

import websocket

URL = "ws://127.0.0.1:8001"
TOKEN = json.load(open(r"D:\deepseek harness\ai-live\vts_token.json", encoding="utf-8"))["token"]


class C:
    def __init__(self):
        self.ws = websocket.create_connection(URL, timeout=8)

    def send(self, mtype, data=None):
        m = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
             "requestID": uuid.uuid4().hex, "messageType": mtype}
        if data is not None:
            m["data"] = data
        self.ws.send(json.dumps(m))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("messageType") in (mtype.replace("Request", "Response"), "APIError"):
                return r


c = C()
print("认证:", c.send("AuthenticationRequest", {
    "pluginName": "ai-live-avatar", "pluginDeveloper": "dsh",
    "authenticationToken": TOKEN}).get("data"))

cur = c.send("CurrentModelRequest").get("data", {})
print("当前模型:", cur.get("modelLoaded"), "|", cur.get("modelName"))

av = c.send("AvailableModelsRequest").get("data", {})
names = [m.get("modelName") for m in av.get("availableModels", [])]
print("可用模型:", names)
print("大肥鱼已加载" if cur.get("modelName", "").startswith("大肥鱼") else "大肥鱼没加载")

if not cur.get("modelName", "").startswith("大肥鱼"):
    target = next((m for m in av.get("availableModels", []) if m.get("modelName", "").startswith("大肥鱼")), None)
    print("目标:", target.get("modelName") if target else None)
    r = c.send("ModelLoadRequest", {"model": target["modelName"]})
    print("加载:", r.get("messageType"), r.get("data"))
    time.sleep(4)
    cur = c.send("CurrentModelRequest").get("data", {})
    print("现在:", cur.get("modelName"))

prm = c.send("InputParameterListRequest").get("data", {})
ids = [p.get("name") for p in prm.get("defaultParameters", [])] + \
      [p.get("name") for p in prm.get("customParameters", [])]
print("参数数:", len(ids), "| 有 ParamMouthOpenY:", "ParamMouthOpenY" in ids)
print("前 12 个:", ids[:12])

print("写 ParamMouthOpenY = 0.85 并回读 …")
c.send("InjectParameterDataRequest", {
    "faceFound": False, "mode": "set",
    "parameterValues": [{"id": "ParamMouthOpenY", "value": 0.85, "weight": 1.0}]})
time.sleep(0.4)
v = c.send("ParameterValueRequest", {"parameterName": "ParamMouthOpenY"}).get("data", {})
print("回读:", v)

print("口型扫 4 秒")
for k in range(120):
    c.send("InjectParameterDataRequest", {
        "faceFound": False, "mode": "set",
        "parameterValues": [{"id": "ParamMouthOpenY",
                             "value": 0.5 + 0.45 * math.sin(k / 8.0), "weight": 1.0}]})
    time.sleep(1 / 30)
c.send("InjectParameterDataRequest", {"faceFound": False, "mode": "set",
                                     "parameterValues": [{"id": "ParamMouthOpenY", "value": 0.0, "weight": 1.0}]})
print("done")
