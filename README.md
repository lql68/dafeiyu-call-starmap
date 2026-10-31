# AI 无人直播：把「图 1 那种直播间」搭出来

目标形态：**AI 自己玩游戏 + 看着画面说人话 + 读弹幕回应 + 点歌 + 打赏兑 Token**，一个人不用出镜。

现在这套已经**跑通并用真画面验证过**（`preview-live.mp4` 就是本机 OBS 录出来的成品画面）。

```
┌──────────────────────────────────────────────────────────────┐
│  OBS 场景  ──▶ 抖音/ B站 RTMP 推流                            │
│                                                              │
│  ① 游戏采集源（Terraria.exe）        全屏 1728x1080           │
│  ② 浏览器源 panel.html               1920x1080 透明叠在上面   │
│        ▲ 每 0.8s 轮询 /state                                 │
│        │                                                     │
│  bridge.js (127.0.0.1:8765)  ◀── POST /push /danmaku /song   │
│        ▲                          ▲                          │
│        │                          │                          │
│   brain.ps1（看画面→决策→注入）   danmaku.py（抖音弹幕）       │
│        │                          ▲                          │
│        ▼                          │                          │
│   sai.ps1  SendInput  ──▶ 游戏真实响应                        │
│   tts.ps1  Claude/SAPI  ──▶ 主播说话                          │
└──────────────────────────────────────────────────────────────┘
```

## 目录

| 文件 | 干什么 |
|---|---|
| `panel.html` | 直播间 UI（顶部 LIVE 条 / TOKEN 卡 / 游戏状态卡 / AI 回复 / 实时弹幕 / 点歌台），中间留空给游戏画面 |
| `bridge.js` | 零依赖状态桥：给 OBS 浏览器源供页面，收各种脚本 POST 的状态 |
| `state.json` | 当前直播状态（自动生成，面板读它） |
| `brain.ps1` | AI 决策循环：OBS 截图 → 视觉模型 → 动作列表 → `sai.ps1` 注入 → 台词推面板 |
| `tts.ps1` | 把台词念出来（Windows SAPI，零依赖；也支持 edge-tts 更好听的音色） |
| `danmaku.md` | 抖音弹幕怎么接（三条路 + B站 10 行版） |
| `preview-live.mp4` | 成品画面录像（面板 + 游戏合成后的效果） |

依赖的底层能力在隔壁 `..\galgame-stream\`：`g.ps1`（OBS 截图）、`sai.ps1`（SendInput 注入）、`obs.ps1`（obs-websocket 控制）。

## 一键起来

```powershell
# 0) 前提：OBS 开着、obs-websocket 4455 开着、泰拉瑞亚在玩
cd 'D:\deepseek harness\ai-live'

# 1) 状态桥
Start-Process node -ArgumentList 'bridge.js' -WorkingDirectory (Get-Location)

# 2) 面板已加进 OBS 场景「Game」（浏览器源 AIPanel，1920x1080 @ 0,0）
#    重新加的话：
#    ..\galgame-stream\obs.ps1 CreateInput -DataFile ..\galgame-stream\req.json
#    （req.json 里 url = http://127.0.0.1:8765/）

# 3) AI 开始玩（每 6 秒一轮）
$env:AI_BASE  = 'https://api.openai.com/v1'   # 任何 OpenAI 兼容端点
$env:AI_KEY   = 'sk-...'
$env:AI_MODEL = 'gpt-4o-mini'                 # 必须支持 image_url
.\brain.ps1 -Loop -Interval 6

# 4) 弹幕（另开一个窗口）
python danmaku.py

# 5) 开播（需要平台给的串流地址+密钥）
..\galgame-stream\obs.ps1 StartStream
```

## 面板怎么改成你自己的

`panel.html` 是单文件，直接改：

- **名字/头像**：`#s-name`、`#pfp`（emoji 或换成 `<img>`）
- **卡片配色**：搜 `rgba(110,168,255` 全局替换色值
- **AI 台词字号**：`#ai .line { font-size:31px }`（图 1 那种是一行 30 字左右，31px 刚好）
- **弹幕条数**：`panel.html` 里 `dm.slice(-6)`，同时在 `bridge.js` 里 `state.danmaku.slice(-12)` 保持一致
- **点歌台行数**：`sg.slice(0,5)`
- **底部免责文案**：`#foot`（抖音要求标注「AI 生成内容」，别删）

改完**不用重启**：OBS 浏览器源右键 →「刷新页面」即可（或在 OBS 设置里给浏览器源开「不可见时关闭」关掉，让它常驻）。

## 抖音开播

1. 手机/电脑装 **抖音直播伴侣**，或用 **抖音开放平台 → 直播 → 推流地址**
2. 拿 `rtmp://...` + 密钥，填进 OBS：
   ```powershell
   Set-Content ..\galgame-stream\req.json '{"streamServiceType":"rtmp_common","streamServiceSettings":{"server":"rtmp://...","key":"..."}}' -Encoding ascii
   ..\galgame-stream\obs.ps1 SetStreamServiceSettings -DataFile ..\galgame-stream\req.json
   ..\galgame-stream\obs.ps1 StartStream
   ```
3. 直播间标题写清「AI 自动游玩」，按平台要求标注 AI 生成内容（图 1 底部那行小字就是干这个的）
4. 竖屏的话：把 OBS 画布改成 1080x1920，`panel.html` 里的 `#dock` 三栏改成纵向堆叠（改 CSS `flex-direction`）

## 变现那层（图 1 的 TOKEN 余额 / 点歌 / 礼物）

面板上那几个数字不是装饰，是**钩子**：

| 元素 | 数据来源 | 触发逻辑 |
|---|---|---|
| `TOKEN 余额 ¥173.53` | `/push token.balance` | 送礼 → `earned` 增加 → 攒够解锁「让 AI 做某件事」 |
| `本轮已赚 ¥37.75` | `/push token.earned` | 同上 |
| `点歌台` | `/song` | 弹幕「点歌 XXX」→ 队列 → 播放到谁的歌就念谁的名字 |
| `实时弹幕` | `/danmaku` | 同时进 `brain.ps1` 的上下文，AI 下一轮会「回应」最近的弹幕 |
| `AI 回复` | `brain.ps1` 出 `say` | 同时走 `tts.ps1` 念出来 = 有声音的 AI 主播 |

接入顺序建议：**先弹幕文本 → 再礼物计 Token → 最后点歌播放**。前两个不做，直播间就是个录屏；做了才有「活人」感。

## 图 2 那种（皮套 VTuber 型）

另一条线，不是游戏：

- **形象**：Live2D（`VTube Studio`）或 3D（`VSeeFace` / `Warudo`），OBS 用**虚拟摄像头或 Spout2** 采集
- **口型**：`VTube Studio` 支持麦克风驱动；或者把 `tts.ps1` 的音频送进虚拟声卡（`VB-Cable`），让皮套跟 TTS 对口型
- **画面**：背景图 + 皮套 + 弹幕纸片（浏览器源叠一层，逻辑和 `panel.html` 完全一样，只是把「AI 回复」换成「弹幕小纸条」）
- **语音**：`tts.ps1` 换 `edge-tts`（`zh-CN-XiaoyiNeural` 很贴图 2 那种声线）

两种形态可以合并：**上游戏、下皮套**（游戏画面占 2/3，右下角小皮套 + 弹幕），这也是现在抖音最常见的布局。

## 已知的坑

1. **`sai.ps1` 必须用 SendInput**，`mouse_event` 在这个游戏里只让按钮高亮、不触发点击（详见 `..\galgame-stream\README.md`）。
2. **OBS 浏览器源的透明**要在源属性里勾「使用自定义 CSS」并填 `html,body{background:transparent}`，否则底部会白一块。
3. **面板轮询 0.8s**，弹幕延迟感约 1 秒；要让弹幕「唰」一下出现，把 `setInterval(tick, 800)` 改 300，或改成 WebSocket（`bridge.js` 里加 `ws` 太麻烦，0.3s 轮询足够）。
4. **AI 决策要限速**：`-Interval 6` 起步。太快会烧 token，太慢会卡在一个动作上重复挖。
5. **模型必须能读图**。纯文本模型喂 base64 会瞎编坐标。
6. 抖音对**无人直播**有风控：要有声音、要有画面变化、别连续几小时同一个静止画面。AI 玩游戏天然满足前两条。