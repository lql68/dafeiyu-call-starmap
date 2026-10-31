# 大肥鱼 · 通话页 + 记忆星图

一个跑在本机的「虚拟形象视频通话」页面，加一张把长期记忆画成星图的可视化。

不是演示视频，是能真用的东西：她看得见摄像头里的你，听得懂你在说什么，用克隆出来的声音回答，
记得住你昨天说过的话 —— 然后这些记忆会变成星图上一颗颗能点开的星。

```
┌─ 通话页 live.html ───────────────────────────────────┐
│  暖色书房背景（ComfyUI 生成）                          │
│  Live2D 立绘（跟真模型，转头 / 眨眼 / 说话开口）         │
│  HUD：记忆条数 · 检索延迟 · 摄像头亮度 · 你的表情        │
│  底部：麦克风 · 输入框 · 摄像头开关 · 背景切换 · 时间轴   │
└─────────────────────────────────────────────────────┘
                  ↓ 点右上角那颗识海球
┌─ 记忆星图 starmap.html ──────────────────────────────┐
│  900 颗星、3823 条边，中心是 M87 那样的黑洞             │
│  四层：黑洞(枢纽)/恒星(人物·重要)/星云(话题)/尘埃(零散)  │
│  搜索 · 7 个类别页签 · 时间轴 · 点星星看完整记忆         │
└─────────────────────────────────────────────────────┘
```

## 文件分工

| 文件 | 干什么 | 依赖 |
|---|---|---|
| `live.html` | 通话页全部前端 | 浏览器（WebGL2） |
| `starmap.html` | 记忆星图，单文件可双击打开 | 浏览器（canvas 2D） |
| `voice_server.py` | 语音合成、`/api/talk`、MJPEG 摄像头、静态服务 | Python 3.11+、TTS 模型 |
| `vision/vision.py` | 摄像头采集 + MediaPipe 人脸 + VAD + 语音转写 | ffmpeg、MediaPipe |
| `gen_memory_graph.py` | 从记忆库导出星图数据 | 只读 SQLite |

细节都在 [README-通话.md](README-通话.md)（三十多页，含每次踩坑的现场）。
更早的无人直播那套在 [README-直播.md](README-直播.md)。

## 它怎么串起来的

```
浏览器                      voice_server.py             AstrBot 插件
  │ 说话/打字 ───────────────→ /api/talk ──────────────→ /turn
  │                            │                          ├ 检索长期记忆
  │  ←──────── { text } ───────┘                          ├ 人格设定
  │                                                       └ 大模型
  │ ←──── /api/say (TTS wav) ←─ IndexTTS2 ← 参考音频（克隆音色）
  │
  │ ←──── /cam.mjpg (MJPEG) ── vision/latest.jpg ← ffmpeg ← 摄像头
  │ ←──── state-vision.json ── 亮度 / 动作 / 人脸 / 听到的话
```

- **看得见**：`vision/vision.py` 一直开着 ffmpeg 抓摄像头，每 3 帧跑一次 MediaPipe，
  算出「正对镜头 / 侧过脸 / 低头」「笑的程度」「眼睛睁多大」；`think()` 把这些写进提示词，
  所以她能说出「这么晚才来，眼睛都睁不开了吧」。
- **听得懂**：同一进程做 VAD 断句 + faster-whisper 转写，`heard` 一更新页面就去 `/api/talk`。
- **记得住**：通话内容每 6 轮由后台任务蒸馏成一条记忆（第三人称、带日期）写进 livingmemory，
  QQ 那边也检索得到同一条。

## 快速开始

```bash
# 1. 摄像头与语音（后台常驻）
python vision/vision.py --snap-every 5

# 2. 服务（首次启动要加载 TTS，约 50-200 秒）
python voice_server.py --port 8770

# 3. 打开 http://127.0.0.1:8770/
```

`voice_server.py` 里的模型路径（`D:\index-tts`、`D:\sakana-py`）是这台机器的布局，换机器要改。
星图不用起服务，双击 `starmap.html` 就能看。

## 记忆星图的数据从哪来

`gen_memory_graph.py` 只读地打开 livingmemory 的 SQLite：

```bash
python gen_memory_graph.py            # 生成 memory-graph.json + 内联进 starmap.html
python tools/make_sample_graph.py     # 生成脱敏示例（仓库里放的就是这个）
```

- 取 `graph_nodes` 里度数最高的 **900** 个，和两端都在集合内的边（**3823** 条 / 库里 5400 条）
- 布点：Fibonacci 球面撒点 → 沿真实边做 6 轮「弹簧 + 回归球面」→ 有关系的记忆自己聚成团
- 半径按 `log2(1+度数)` 分层，颜色按节点类型，亮度按深度 + `created_at` 新近度
- 画线按平均深度分档，每档一次 `beginPath`，3800 条线也只有 4 次 `stroke`

> 仓库里的 `memory-graph.sample.json` 和 `starmap.html` 内联的数据**已经脱敏**：
> 保留拓扑、类别、度数、坐标、重要性，实体名和记忆正文换成占位内容。
> 自己跑 `gen_memory_graph.py` 得到的是真数据。

## 踩过的坑（代码注释里都有现场）

- **鼻梁上的黑块**：Cubism 的 `dynamicFlags & 1` 是 isVisible，漏判会把遮罩网格当普通网格画出来。
  最后在 pixi 里按「尺寸 + 亮度」筛候选、逐个隐藏验证，定位到第 513、514 号网格。
- **摄像头延迟 94ms → 39ms**：`-fflags nobuffer -flags low_delay -probesize 32`、
  每帧都写 `latest.jpg`（不是每 2 帧）、消费者用条件变量等而不是 50ms 轮询。
- **流式 TTS 的爆音**：IndexTTS 流式 yield 的是 int16 量级的 float，
  按 `clip(x,-1,1)*32767` 处理会把整段压成方波。先判 `max(|a|) > 4` 再除 32768。
- **点识海球卡死**：`/cam.mjpg` 是永不结束的流，占着同域 6 个并发连接里的一个，
  iframe 的请求就排队。打开星图前先把 `<img src>` 摘掉。
- **`.hud{pointer-events:none}`** 会传给整棵子树，控制条全点不动 —— 需要点的显式收回 `auto`。

## 已知限制

- 只在 Windows 上跑（DirectShow 采摄像头）
- TTS 要 5 GB 显存，和本地大模型抢同一张卡，得错峰
- 星图在 4K + 放大 3 倍时掉到 30fps 左右（视锥剔除、按 zoom 限边都做了）
- 说完到听见约 4-6 秒（大模型 1-1.5s + TTS 首包 2.4-3.3s）

## 署名

Live2D 模型「大肥鱼」：

> 原画及拆分 **神宫凉子** · Live2D 建模 **霓虹猫_NeonNeko** · 模型来源 **神宫凉子免费配布模型**

模型文件不随仓库分发（作者授权禁止重新分发）。`bg/` 下三张背景由本项目的 ComfyUI 工作流生成。

## License

代码 MIT。模型、参考音频、真实记忆数据不在授权范围内。