# 弹幕接入：抖音直播间弹幕怎么拿到

直播间面板（`panel.html`）只要往 `http://127.0.0.1:8765/danmaku` POST 一条 `{"user":"是谁","text":"说了什么","gift":false}` 就会滚动显示。所以**真正的问题只有一个：弹幕从哪来**。

下面三条路，按上手难度排序。

---

## 路线 A：第三方抓取库（最快，10 分钟出效果）

抖音网页版直播间（`live.douyin.com/<房间号>`）走的是 WebSocket：
`wss://webcast*.douyin.com/webcast/im/push/v2/...`，带 `signature`、`ttwid`、`msToken`、`X-Bogus` 等参数。

自己算签名很痛苦，直接用社区项目：

| 项目 | 语言 | 说明 |
|---|---|---|
| `saermart/DouyinLiveWebFetcher` | Python | 最常用的抖音直播弹幕抓取，含签名、支持评论/礼物/进场/点赞 |
| `pykiller/dy-live` | Python | 轻量封装，回调式 |
| `ihmily/DouyinLiveRecorder` | Python | 主打录制，但也能取弹幕 |

装完接线（伪代码，把它当适配器，不要改动内部）：

```python
# danmaku.py
import json, requests
from DouyinLiveWebFetcher.live import DouyinLiveWebFetcher

BRIDGE = "http://127.0.0.1:8765"

def push(user, text, gift=False):
    requests.post(BRIDGE + "/danmaku", json={"user": user, "text": text, "gift": gift}, timeout=3)

def on_message(msg):
    # 库会把消息回调出来，按类型分发
    if msg["type"] == "comment":
        push(msg["nickname"], msg["content"])
    elif msg["type"] == "gift":
        push(msg["nickname"], f'送了 {msg["gift_name"]} x{msg["repeat_count"]}', gift=True)
        # 礼物驱动玩法：加 Token / 触发动作
        requests.post(BRIDGE + "/push", json={"token": {"earned": msg["diamond"] * 0.1}}, timeout=3)

if __name__ == "__main__":
    DouyinLiveWebFetcher("房间号或 https://live.douyin.com/xxx", on_message).start()
```

> 需要 `pip install requests websocket-client protobuf` 等依赖，按项目 README 来。
> 房间号就是 `live.douyin.com/` 后面那串数字。

---

## 路线 B：抖音开放平台（正规、稳定、要资质）

「直播开放能力 / 直播小玩法 / 互动玩法」里可以订阅**直播间评论事件**，走官方长连接推送，带签名校验。

- 需要：开发者账号 + 应用审核 + 主播授权（`Webcast` 相关 scope）
- 优点：不怕封、不会因为抖音改签名就挂、能拿礼物/点赞/进场全量事件
- 缺点：审核周期，且是给「小玩法」用的，纯直播间可能要求走「直播伴侣」侧

如果打算长期做、还要接礼物计费，这条路才是终局。

---

## 路线 C：直播伴侣 + OCR/剪贴板兜底

开「抖音直播伴侣」→ 评论区浮窗 → 屏幕区域 OCR（如 `RapidOCR` / `PaddleOCR`）或读伴侣的评论日志。

- 优点：零逆向、不被限流
- 缺点：延迟 2-5 秒、昵称容易识别错、礼物信息抓不全

应急可用，不建议当主线。

---

## 顺手说 B 站（更好接）

如果对平台没绑定，B 站直播间弹幕是**明文 WS，无需签名**：

```python
# pip install blivedm
import asyncio, requests
from blivedm import BLiveClient

class C(BLiveClient):
    async def _on_danmaku(self, client, msg):
        requests.post("http://127.0.0.1:8765/danmaku",
                      json={"user": msg.uname, "text": msg.msg}, timeout=3)

asyncio.run(C(room_id=你的房间号).start())
```

10 行跑通，适合先把「AI 看弹幕回话」这条逻辑验证透，再上抖音。

---

## 弹幕 → 玩法的钩子（图 1 里那些东西）

| 弹幕/事件 | 面板动作 | 游戏动作 |
|---|---|---|
| 普通评论 | POST `/danmaku` | 进 AI 上下文，下一轮决策会考虑 |
| 「点歌 XXX」 | POST `/song` | 播放队列（网易云 API 或本地曲库） |
| 送礼物 | POST `/danmaku` + `/push token.earned` | 加 Token、解锁动作（如「放毁灭菇」） |
| 关注/进场 | POST `/danmaku`（gift=false, 前缀灰色） | 语音欢迎 |

AI 回复长度控制：图 1 底部写着「30 字内回复」—— 在 `brain.ps1` 的 system prompt 里已经限制成 15 字，按需改。