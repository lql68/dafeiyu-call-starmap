# 她 · 视频通话页

一句话：双击 `start-all.ps1`，等 50 秒左右浏览器自己开出来，点「接 通」。

---

## 怎么开 / 怎么关

```powershell
powershell -ExecutionPolicy Bypass -File "D:\deepseek harness\ai-live\start-all.ps1"
```

它会按顺序做四件事：

```
[1/4] 看门狗已恢复
[2/4] 已让看门狗拉起服务（模型加载约 50-60 秒）
[3/4] 等语音服务........
[4/4] 就绪  → 自动打开浏览器
```

关掉：

```powershell
powershell -ExecutionPolicy Bypass -File "D:\deepseek harness\ai-live\stop-all.ps1"
```

```
[1/3] 看门狗已停用（不会再把服务拉回来）
[2/3] 关掉 3 个进程
[3/3] 8770 已释放，摄像头/麦克风已松开
```

> **摄像头是独占的。** 微信视频 / OBS / 腾讯会议开着的时候采集会起不来，先停（或先跑 stop-all）。

### 为什么要有「看门狗」

`Start-Process` 起的子进程会跟着调用它的窗口一起死 —— 包括 DSH 自己崩掉的时候。所以这套服务**不由脚本直接起**，而是交给任务计划程序里的 `ai-live-watchdog`（每 2 分钟跑一次）：

- 8770 没在监听 → 起 `voice_server.py`
- 没有 `vision.py` 进程 → 起采集

`stop-all.ps1` 会 **先停用这个任务、再写 `svc\paused.flag`**，然后才杀进程。少了这一步，服务会在 2 分钟内自己回来 —— 这就是"关不掉"的真正原因。`start-all.ps1` 反过来做：删 flag、启用任务、立刻跑一次。

任务不存在时这样重建（一次性）：

```powershell
$act = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\deepseek harness\ai-live\svc\watchdog.ps1"'
$trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "ai-live-watchdog" -Action $act -Trigger $trg -Settings $set -Force
```

> **改 `.ps1` 时必须存成 UTF-8 带 BOM。** PowerShell 5.1 会把无 BOM 的 UTF-8 当 GBK 读，中文注释里的引号被吃掉后整个脚本报「字符串缺少结束符」，一行都不执行 —— 这就是 `stop-all.ps1` 之前"失效"的原因。

---

## 页面参数

| 网址 | 作用 |
|---|---|
| `http://127.0.0.1:8770/` | 正常用，要点一下「接 通」 |
| `.../?auto=1` | 自动接通（截图 / 无人值守） |
| `.../?auto=1&mouth=1` | 口型自己开合，用来看唇形对不对 |
| `.../?auto=1&mouth=0.6` | **固定张开度**（0~1），验收单帧口型用 |

浏览器必须**用户手势**才允许出声，所以正常入口留了那个闸。

---

## 整条链路

```
你说话 → vision.py 断句（600ms 静音算说完）→ POST /api/hear
        → faster-whisper base 识别 → 写进 state-vision.json 的 heard
        → 页面 poll 到 heard.seq 变了 → POST /api/think
        → qwen2.5:3b 按 persona.txt + 最近 6 轮上下文 回一句
        → POST /api/say → IndexTTS2 用 refs/her_timbre_breathed.wav 音色合成
        → 后处理：atempo 1.39 + 标点处插 70ms 静音 + loudnorm
        → tts/voice/<hash>.wav → <audio> 播放
        → AnalyserNode 的真振幅驱动嘴型 + 26 根音量条，字幕按播放进度逐字打
```

她一直不说话超过 28 秒会自己嘟囔一句。

**为什么要那三步后处理**：纯合成结果唱腔指数 1.11（比原歌还像在唱），因为参考音频是首歌，
模型连"一口气不换气"的节奏一起学了。atempo 变速保音高、静音插在标点处 —— 两步把唱腔压到
0.33，音色损失只有 0.79 → 0.68。这是扫了 v9–v13 五轮之后唯一能用的方案（WORLD 域一碰音色就崩）。

### 三个接口

| 接口 | 干什么 |
|---|---|
| `POST /api/say` `{text}` | 合成并返回 `{url,dur,cached}` |
| `POST /api/think` `{text,scene,history}` | 回一句，返回 `{text,ms,model}` |
| `POST /api/hear`（body 是 16k mono wav 字节） | 识别，返回 `{text,dur,ms}` |

- 想换音色：改 `voice_server.py` 顶部 `HER` 指向别的 wav，**24k mono**，8–10 秒干净说话声最好
- 想调语速：`voice_server.py` 里的 `FACTOR`（1.39 = 快 39%），越大越像说话，越小越像唱
- **想改她的脾气：直接改 `persona.txt`，存盘就生效，不用重启**（重启要等 50 秒加载模型）
- 生成过的句子按内容 hash 缓存，同一句第二次 0.02 秒返回

---

## 显存 / 内存（重要，会崩）

- TTS 常驻 **5GB 显存**，显卡 8GB。
- 接话模型用 ollama 的 `qwen2.5:3b`，全上 GPU 要 2GB → 两个一起 7.6G/8.1G，**一挤就崩**。
  现在用 `AI_LIVE_NUM_GPU=16` 让 3b 部分卸载，实测 **6.6G/8.1G、空闲 1.3G**，接话 0.5–0.8 秒（首次 7.6 秒）。
- `start-all.ps1` 已经带上这个环境变量。
- **这台机器内存 15.2G 真的不够**。开着 Comfy Desktop（0.6G）+ AstrBot + SnowLuma + 浏览器时，
  空闲只剩 1.2G，显卡那边一失败（llama-server 的 `0xc0000409`）会顺手把 TTS 的 python 一起带走
  （`torch_cpu.dll` 的 `0xc0000005`）。用通话页之前把 ComfyUI、OBS 关掉。

---

## 她怎么"看见"你

`vision.py` 常驻一路视频 + 一路音频 ffmpeg，python 只读管道：

- 视频 640x480@15 → `state-vision.json` 里的 `brightness`（真实帧平均亮度）、`motion`（帧差）、`fps`
- 音频 16kHz → `rms` / `peak`，维护自适应底噪基线（中位数），超过基线 2.6 倍且 peak>0.05 才算"你在说话"
- 说完 600ms 静音 → 把那一段（最多 15 秒）POST 给 `/api/hear`，识别结果写进 `heard`

页面每 500ms 读一次这个 json。HUD 上那些数字**全是真的**：
`MEMORY USAGE` 是采集帧数、`AMBIENT BRIGHTNESS` 是当前画面亮度、`MOTION` 是帧差、
`听着` 是刚识别出的话、`接话` 是模型这次的耗时，摄像头小窗就是 `HD webcam` 的实时帧。

> 不想说话又想测她接话：往 `say.txt` 写一句话存盘，`vision.py` 会在 0.4 秒内把它当成"你说的话"注入。

---

## 嘴型怎么动的

**不是切图**。`chibi_closed.png` 是把原图的嘴用 `cv2.inpaint` 抹掉、只留一条淡唇线的版本，
嘴是 `.mouth > .cavity` 这个**参数化椭圆**按音频实时画的：

- `--open`（0–1）：张开度，由她输出音频的 RMS 决定，**快起慢落**（0.5 / 0.2）才像牙关
- `--wide`（0.9–1.26）：由**谱质心**决定 —— 低频（啊、哦）嘴圆，高频（衣、诶）嘴扁
- `--roll`：±1.6° 微摆，不让人看出是贴片
- 里面还有 `.teeth`（张嘴初期露牙，open 越大越淡）、`.tongue`（open > 0.4 才出现）、`.lip`（上唇投影）

麦克风的说话声不驱动嘴 —— 不然你咳嗽她也张嘴。

---

## 五官坐标

在 5% 网格放大图上量的：

- 眼左 `34.0% / 40.1%`，眼右 `52.2% / 40.0%`
- 嘴 `42.9% / 45.6%`

**改立绘就要重新量**。`.fx` 的 `layoutFx()` 会自动把叠层对齐到 `object-fit:contain` 的实际绘制区，
不用管 letterbox。

---

## 2.5D 分层：头会转、尾巴会摆

没有 Live2D 模型文件（`.moc3` 只能由 Cubism Editor 导出），所以这里走的是**不拆图、不补洞**的路线：
把同一张 `chibi_closed.png` 叠四层，每层用**羽化蒙版**裁出一块区域，各自的 transform 不同。

| 层 | z | 蒙版 | 动什么 |
|---|---|---|---|
| `.back-l` | 0 | 无（原图整张） | 不动，专门补住别层挪开后的空洞 |
| `.tail-l` | 1 | `mask_tail.png`（按颜色锁尾鳍） | 绕尾根 `77% 79%` 摆 ±3° |
| `.body-l` | 2 | `mask_body.png`（= 1 − 头 − 尾） | 只有呼吸 |
| `.head-l` | 3 | `mask_head.png`（椭圆 + 底部软切） | 绕颈部 `50% 52%` 转 ±3.2°、微缩放 |

关键点：

- **蒙版必须存成 RGBA，用 alpha 当遮罩**。灰度图 alpha 全是 255，CSS 会当成"不遮"= 蒙版失效。
- **三层之和恒为 1**（`body = 1 − head − tail`），所以静态时不会出现重影；`make_parts.py` 会打印
  `不透明区内三层之和: min/mean/max` 来自检。
- **旋转轴心放在接缝点上**（颈部 / 尾根）。轴心在接缝上，接缝就不动，只有远端摆——这是不穿帮的全部秘密。
- 轴心别用位移，用**旋转 + 微缩放**。纯平移会把整层挪走，接缝两侧立刻裂开。
- `mask_tail.png` 不能用椭圆（会连带切到裙子，一转就穿帮），也不能漫水（会被深色描边漏出去），
  最后是按尾鳍专属的靛蓝 `R 30–90 / G 55–115 / B 125–195 / R÷B < 0.5` 锁出来的。

驱动（`live.html` 的 `poseStep`）：

- 鼠标位置 → `poseX/poseY`（±1），低通后映射成旋转与位移
- **2.6 秒没动鼠标，她自己东张西望**（每 1.5 秒随机换一个目标方向）
- 说话时（`.mouth.open`）加一点 `sin(t/145)` 的点头
- `?pose=1` 强制最大偏移，用来查接缝

重新生成蒙版：

```
D:\sakana-py\python.exe "D:\deepseek harness\ai-live\live2d\make_tail.py"   # 尾鳍蒙版
D:\sakana-py\python.exe "D:\deepseek harness\ai-live\live2d\make_parts.py"  # 头/身（读上面的尾）
```

两个脚本都必须用 `D:\sakana-py\python.exe`（Medium 完整性级别）+ 把 AstrBot 的 site-packages
挂进 `sys.path` 才有 numpy/cv2。诊断图在 `chibi/parts/zones.png`、`zones_tail.png`。

> 想要**真 Live2D**（可眨眼带动眼周、头发物理、口型音素映射）需要：装 Cubism Editor →
> 画师出分层 PSD（刘海 / 前发 / 后发 / 眼白 / 虹膜 / 睫毛 / 脸 / 身体 / 尾，且被遮挡处要补画）→
> 在 Cubism 里绑参数 → 导出 `.moc3` + `.model3.json` → 页面换 `pixi-live2d-display`。
> 现在的四层方案是上层，换成真模型只动立绘那一块，HUD / 语音 / 口型参数都能复用。

---

## 文件

| 文件 | 是什么 |
|---|---|
| `live.html` | 整个页面（HTML+CSS+JS 单文件，~700 行） |
| `voice_server.py` | 静态服务 + say/think/hear 三个 API，单端口 8770 |
| `persona.txt` | 她的语气提示词，改了存盘即生效 |
| `say.txt` | 调试用：写一句话进去 = 假装你说了这句 |
| `vision\vision.py` | 摄像头/麦克风采集 + 断句 + 调 ASR，写 `state-vision.json` |
| `start-all.ps1` / `stop-all.ps1` | 一键起 / 停 |
| `chibi\` | 立绘两张 + 标定用网格/对比图 |
| `tts\refs\` | 参考音频（`her_timbre_breathed.wav` 是当前用的） |
| `tts\voice\` | 合成缓存 |
| `tts\*.py` | 实验脚本：`final_clone.py`（当前方案）、`clone_v9~v13`（失败的那些，留着看为什么失败）、`eval_gen.py`（音色×唱腔打分） |

---

## 还没做的

- **嘴型是按音量连续变化，不是按音素**。要精确到「啊/衣/呜」得先拿到音素边界（ASR 能出时间戳）再映射到 `--wide`/`--open` 的目标值，现在 `--wide` 用谱质心近似，方向对但不精确
- **她只有嘴和呼吸会动**，没有眨眼之外的头部动作、没有手势。真要全身动得上 Live2D 或 VRM
- 参考音频仍是那首歌里最干净的一段（音色 0.772）。换一段真正说话的录音能直接上 0.83+，这一步只差素材
---

## 接 AstrBot：让她和 QQ 上的自己是同一个人

`voice_server.py` 的 `think()` **优先问 AstrBot**，问不到才回落到本地 ollama：

```
通话页 --POST /api/think--> voice_server --POST 127.0.0.1:7902/turn--> AstrBot(插件) --text_chat--> deepseek/deepseek-flash
                                                                                          + 人格「大肥鱼」
QQ 消息 --> AstrBot 生成回复 --> 插件 on_llm_response --> POST {avatar_url}/api/say --> 立绘开口
```

### 插件：`AstrBot/data/plugins/astrbot_plugin_live_avatar/`

自己起一个只绑 `127.0.0.1:7902` 的 `asyncio` TCP 服务，手写极简 HTTP/1.1（POST/GET + Content-Length + 短连接），
**不走 `register_web_api`**——那套路由由 Dashboard 统一鉴权，外部调用要 JWT，太绕。

| 接口 | 说明 |
|---|---|
| `GET /health` | `{ok, provider, persona}`，查当前用的是哪个模型、哪个人格 |
| `POST /turn` | `{text, scene, history}` → `{ok, reply, ms, persona}` |

`/turn` 做的事：`context.get_using_provider()` 拿模型 → `persona_manager.get_default_persona_v3()` 拿人格
（字段是 `prompt`，不是 `system_prompt`）→ 把场景串拼进系统提示词 → `provider.text_chat()` → 取 `.completion_text`。

> **注意** `agent_runner.runner_type=local` 时走 Agent runner，带工具和长期记忆；`text_chat()` 是直连模型，
> **不经过 Agent runner，所以不带工具调用和 livingmemory 的检索**。实时语音场景要的是 1 秒内出话，
> 128 步的 Agent 跑不动，这是有意的取舍。要记忆就在 `history` 里多带几条。

`_conf_schema.json` 可调：`enabled` / `listen_port`(7902) / `avatar_url`(8770) / `push_qq_reply` / `push_max_chars`(60) / `session_umo`。

**改了插件必须重启 AstrBot**：热重载要有 `ASTRBOT_RELOAD=1` 环境变量，默认关着。

### voice_server 侧

```python
ASTRBOT = os.environ.get("AI_LIVE_ASTRBOT", "http://127.0.0.1:7902")
ASTRBOT_ON = ASTRBOT.lower() not in ("off", "", "0", "none")
ASTRBOT_TIMEOUT = int(os.environ.get("AI_LIVE_ASTRBOT_TIMEOUT", "25"))
```

- `AI_LIVE_ASTRBOT=off` → 只用本地 ollama（不需要 AstrBot）
- 桥没起 / AstrBot 没跑 → 打一行 `[think] AstrBot 不可用，回落本地 ollama`，然后照常工作，**不会卡**
- `/api/think` 返回的 `model` 字段会显示 `astrbot/大肥鱼`，一眼看出这次是谁出的话

### 实测

| 环节 | 结果 |
|---|---|
| `GET /health` | `{"ok":true,"provider":"deepseek/deepseek-flash","persona":"大肥鱼"}` |
| `POST /turn` 一句抱怨累的测试句 | 1356ms → （回了一句关心的话，内容略） |
| `POST /turn` 空文本（她主动开口） | 1407ms → （主动说了半句，内容略） |
| `POST /api/think` | 1288ms → `model=astrbot/大肥鱼` |
| `POST /api/say` → TTS | 9360ms（首次含 warmup）→ 3.17s wav |
| 整页连跑 | 接话 1694ms，字幕正常打出她的回复（内容略） |
---

## 接 AstrBot 的长期记忆（livingmemory）

通话页现在读的是 **QQ 上同一份记忆库**。她在电话里提的事、在 QQ 里提的事，是同一批。

**怎么接的**

```
通话页 /api/think → voice_server → POST :7902/turn
                                      ↓
                        astrbot_plugin_live_avatar
                                      ↓ star_map 找 LivingMemoryPlugin
                        livingmemory.memory_engine.search_memories(
                            query=他说的这句, k=5,
                            session_id=napcat:FriendMessage:<你的 QQ 号>)
                                      ↓ 拼成 5 条 → 塞进 system prompt
                               deepseek-flash + 大肥鱼人格 → 回话
```

**配置**（`AstrBot\data\config\astrbot_plugin_live_avatar_config.json`）

| 键 | 值 | 说明 |
|---|---|---|
| `session_umo` | `napcat:FriendMessage:<你的 QQ 号>` | 用哪份会话的记忆/人格；这是你和她的私聊 |
| `memory_enabled` | `true` | 关掉就退回「无记忆」模式 |
| `memory_top_k` | `5` | 每次捞几条 |
| `memory_timeout` | `8` | 超时就当没记忆，绝不拖慢接话 |

**实测**（每轮注入 5 条，接话总耗时 1.3–1.9 秒）

| 问什么 | 她的表现 | 来源 |
|---|---|---|
| 「上次我说想吃什么来着」 | 说出一个具体菜名，其中一处记混了 | 记忆库 |
| 「你还记得我前几天干了啥吗」 | 提到了那件事的两个细节，还追问了一句 | 记忆库 |
| 「你上次说想养什么来着」 | 准确说出那个东西 | 记忆库 |
| （她主动开口，上下文刚提过某个工具） | 顺着上下文接了一句 | 上下文 |

> 具体对话内容略 —— 那是真实记忆库跑出来的，不适合放进公开仓库。

**三个坑**

1. **livingmemory 初始化要 15 秒**。AstrBot 启动后约 40 秒内 `initializer.memory_engine` 还是 `None`，这期间插件自动降级成「不带记忆」，不会报错也不会卡。等它起来就恢复了。
2. **`documents` 表的正文列叫 `text`，不是 `content`**。直接查库会踩 `no such column: content`。
3. **改插件必须重启 AstrBot**。热重载默认关（要 `ASTRBOT_RELOAD=1`），改完 `main.py` 不重启等于没改。

**通话不写记忆**：这轮对话不会进记忆库（写记忆走 QQ 的 LLM 请求链路）。想让通话也留痕，得再开一条写入路径。
---

## 怎么启动（三个入口，都实测过）

| 怎么点 | 会发生什么 |
|---|---|
| **双击 `启动.bat`** | 最省事。跑完停在窗口里，能看到红字；服务在后台继续跑 |
| `powershell -EP Bypass -File start-all.ps1` | 命令行里跑，结束后窗口关掉 |
| `start-all.ps1 -Force -NoBrowser` | 内存不够也强启；不弹浏览器 |

停止：双击 `停止.bat`，或 `pwsh -File stop-all.ps1`。

**为什么以前"运行不了"**

- **双击 `.ps1` 不执行**：Windows 默认把 `.ps1` 关联到记事本，双击只是把源码打开。要双击运行就得用 `.bat`，所以给了 `启动.bat`。
- **右键「使用 PowerShell 运行」窗口一闪就没**：脚本里有 `Read-Host` 问"内存不够还继续吗"，非交互拿不到输入就直接 `exit 1`，窗口立刻关，什么都看不到。
- **错误被吞**：旧版开头 `$ErrorActionPreference = 'SilentlyContinue'`，`Get-ScheduledTask` 失败也不吭声。

**现在的行为**

- 内存检查：低于 **2.5 GB** 才警告；交互式会问一句，非交互（管道/计划任务）自动继续并说明。
- 每一步 `try/catch`，失败打红字 + 提示"以管理员身份重新运行"。
- 3 分钟等不到 `/api/status` 就打印 `voice_server.err.log` 的最后 8 行，不用自己去翻。
- `install-task.ps1`：看门狗任务被删了就重装，顺手给三个 `.ps1` 补 UTF-8 BOM（PowerShell 5.1 不认无 BOM 的中文脚本，会报「字符串缺少终止符」）。
---

## 真 Live2D：换成「大肥鱼」官方模型

桌面那套 `DeepSeek免费公皮\DeepSeek\` 是完整可用的 Live2D 模型，已搬进项目：

```
ai-live/live2d/
  model/大肥鱼/          moc3 15.7MB · 5 张 4096 贴图 · 23 个表情 · 8 个动作 · physics3
  lib/                   live2dcubismcore.min.js · pixi.min.js 6.5.10 · cubism4.min.js 0.4.0
  test.html              裸模型测试页（独立验证模型能不能跑）
  patch_model.py         给副本补 Motions / Expressions / LipSync 声明（原文件只有 Moc/Textures/Physics）
```

**做法**：把原来的「四层拆图 2.5D」整套换成一个 `<canvas>`，用 pixi-live2d-display 渲染。

- 取景：`BUST = 0.42` 头肩，`?frame=full` 看全身。**头肩取景要顶对齐**（`y = -oh*s*0.015`），
  全身取景才底对齐（`y = h-oh*s`）——按底对齐会把头切掉，只剩腿。
- 参数必须在 `internalModel.on('beforeModelUpdate')` 里写，`coreModel.update()` 之后写的会被覆盖。
- 嘴：`ParamMouthOpenY` 直接吃 TTS 输出音频的 RMS（和原来的口型同一套 `mouthP`）。
- 眼睛：模型自带 EyeBlink + 自动眨眼，不用手写。
- 表情：正则匹配她这句话的情绪 → 喂 `Exp3` 里对应表情（圈圈眼/爱心眼/流泪/脸红/屑屑眼…），6 秒回 `默认体型`。
- 动作：`Animation/` 里 8 个动作组，走 pixi 的 idle motion。
- 头摆：鼠标跟随 + 2.6 秒不动就自己东张西望，同时驱动 `ParamAngleX/Y/Z`、`ParamBodyAngleX/Y`、`ParamEyeBallX/Y`。

**署名（授权要求，已写进页面右下角）**：原画及拆分 神宫凉子 · Live2D 建模 霓虹猫_NeonNeko · 模型来源 神宫凉子免费配布模型。
个人直播/视频/二创可用（含收益），**不可二次销售、不可重新分发模型文件**。

**已知问题**：她两眼之间（鼻梁上方）有一个黑色小图标，是模型自带的一个道具图层。
VTube Studio 里它是关着的，网页里没人替她关掉。试过的：`?nomouth=1`、按 Part 名隐藏、
把 715 个 drawable 逐个透明、把 `key1~13 / Movement1~3 / Clothes1~5` 参数清零 ——
都没反应，因为 **pixi-live2d-display 0.4.0 不读运行时改的 drawable/part opacity**（它只认参数）。
下一步要么用 VTube Studio 当渲染器，要么换个还在维护的 Live2D web 运行时。

## 真 Live2D 走 VTube Studio + OBS（当前最完整的一条）

网页里那条 canvas 路线有个治不好的毛病：模型鼻梁上多一块黑色小图标（pixi-live2d-display 0.4.0 把一个裁剪遮罩网格当普通图渲染了）。同一份 .moc3 用 VTube Studio 的官方渲染器打开**完全干净**。所以最终形态改成「VTS 负责渲染，OBS 负责合成」。

### 链路

`
网页 (8770, ?render=vts&nohint=1)  ─┐
                                   ├─ OBS 场景「通话页」─→ 投影窗口 / 录制 / 虚拟摄像头
VTube Studio (8001, 透明推流) ─────┘
        ↑ 口型 / 表情由 voice_server 的 /api/mouth、/api/vts/expression 驱动
`

### VTS 侧要点

| 事 | 怎么做 |
|---|---|
| 打开 API | VTube Studio_Data\StreamingAssets\Config\vts_config.json 里 Config_StartAPI 改成 	rue，重启 VTS，8001 才监听 |
| 授权 | 第一次连会弹窗，点允许；token 存在 i-live\vts_token.json |
| 模型 | 拷到 StreamingAssets\Live2DModels\大肥鱼\；大肥鱼.model3.json 原来缺 name 字段，要补上 |
| 透明推流 | VTS 里打开「透明推流」开关——**它只影响采集，不会让桌面上的窗口变透明**（本地化文件写得很清楚） |
| 口型 | VTS 不认模型的 ParamMouthOpenY，认它自己的输入参数 **MouthOpen**（127 个输入参数之一），由 VTS 映射到模型 |
| 换模型 | ModelLoadRequest 在「一个模型都没加载」的状态下必定失败（APIError 154），官方模型 Akari 也一样；必须人手在界面里点一次，之后 API 才能换 |
| 窗口 | **别最小化**。游戏采集抓的是渲染表面，缩下去就是黑屏 |

### OBS 侧要点

- 场景名 通话页，两个源：
  - 通话页-页面：浏览器源 → http://127.0.0.1:8770/?auto=1&render=vts&nohint=1
  - 通话页-立绘：窗口采集 → VTube Studio:UnityWndClass:VTube Studio.exe，**允许透明 = 开**、premultiplied_alpha = false
- 页面侧的 
ender=vts 会把 canvas 藏掉、只留 HUD/摄像头/字幕；
ohint 再藏掉「已交给 VTube Studio 渲染」那块占位字。
- VTS 自己的设置面板（调色板、透明推流开关）画在同一个 Unity 窗口里，**会被一起抓进去**，调完记得按 Esc / 点 ✕ 关掉。
- 调整取景用 ..\.tmp\obs_frame.py <目标头x> <目标头顶y> <人像高度px>：它会先量出她在源里的真实包围盒，再反算 OBS 的 scale/pos，一跑就到位。

### 踩过的坑

- obs-websocket 的 Hello 里认证字段在 d.authentication.{salt,challenge}，不是 d.salt；算法 64(sha256(b64(sha256(pw+salt)) + challenge))。
- OpenVideoMixProjector 的 projectorGeometry 不能给空字符串（403），要给 JSON。
- 场景 JSON 里写 pos 0,0 会被 OBS 归一成居中，必须用 SetSceneItemTransform 显式给 positionX/positionY + lignment:5。
- 投影窗口在 150% 缩放的屏幕上如果被裁切，是 OBS 按 1:1 像素渲染、窗口比画布小就裁剪（不是缩放）。想整页不裁，把 OBS 画布改成 1280x720，或用 OBS 主预览看。

---

## 她知道你在笑、在不在看（MediaPipe 人脸）

纯 CPU，**不占显存**（一帧 40 ms，15fps 下每 3 帧跑一次 ≈ 单核 20%）。

### 装法（有坑）

`D:\sakana-py\python.exe` 是 uv 管的环境，直接 `pip install` 会报
`error: externally-managed-environment`。必须装到独立目录：

```
D:\sakana-py\python.exe -m pip install --target "D:\sakana-py\mp" mediapipe
```

装出来是 **mediapipe 1.2.0**，它**已经没有 `mp.solutions` 了**（`hasattr(mp,'solutions')` 为 False），
只有 `mp.tasks`。所以走 `mediapipe.tasks.python.vision.FaceLandmarker`：

- 模型：`vision/models/face_landmarker.task`（3.6 MB，Google 官方 float16/1 版）
- 运行时靠 `sys.path.insert(0, r'D:\sakana-py\mp')`，别动系统 site-packages

### 她拿到的字段

`vision/face.py` 的 `FaceTracker.process(frame)` 返回：

| 字段 | 含义 |
|---|---|
| `present` | 画面里有没有脸 |
| `yaw / pitch / roll` | 头部朝向（度）。正脸实测 yaw -2、pitch 3.5、roll 8 |
| `look` | 正对镜头 / 侧过脸 / 转开头 / 低头 / 抬头 |
| `eyes_open` | 0..1 睁眼程度（用 blendshape `eyeBlinkLeft/Right`，没有就用 EAR 兜底）|
| `smile` | 0..1 嘴角上扬（blendshape `mouthSmileLeft/Right`）|
| `mouth_open` | 0..1 张嘴（`jawOpen`）|
| `gaze_x / gaze_y` | 眼珠偏移（虹膜 468/473 相对眼眶）|
| `dist` | 脸占画面高度，用来判远近 |
| `emo` | 笑 / 张嘴 / 眯眼 / 没在看 / 平静 / 一般 |

### 接在哪

1. `vision.py` 每 3 帧跑一次，写进 `state-vision.json` 的 `face` 字段
2. `live.html`：HUD 第三卡多两行「看着 / 表情」；她的头跟着他的头转
   （`targetX = -yaw/30`、`targetY = -pitch/30`，只在 `|yaw|<45` 时接管，
   否则退回鼠标跟随）；眼珠跟着他的眼珠（`ParamEyeBallX/Y`）
3. `voice_server.py` 的 `think()`：把「他在笑 / 他低头 / 他眯着眼像是困了 / 镜头里没看到他的脸」
   拼进场景串，所以接话会真的用上这些。实测：`eyes_open 0.3` →
   （她据此说了句「看你要不要早点躺下」意思的话）

### 标定过的坑

- 一开始用 `cv2.solvePnP` 解姿态，结果 `roll = -170.3`（解翻 180°）。改成**关键点几何量**：
  `roll = atan2(eyeR.y-eyeL.y, eyeR.x-eyeL.x)`、
  `yaw = atan2(nose.x-eyeMid.x, faceW*0.5) * 1.55`、
  `pitch = (0.32 - (nose.y-eyeMid.y)/(chin.y-eyeMid.y)) * 120`
  （0.32 是正脸时鼻尖的相对位置，实测 0.295）
- `detect_for_video` 的时间戳必须**严格递增**，否则报错；代码里有 `_last_ts` 兜底
- `state-vision.json` 偶尔 `os.replace` 报 `WinError 5`（正好有人在读）→ 加了 5 次重试
- `vision.py` 里给全局 `FT` 赋值必须写 `global FT`，否则 `UnboundLocalError`

## QQ 和网页是同一个她（双向通道）

之前有个断层：QQ 上她回的话只存在 QQ 里，网页那边完全不知道——因为插件的
_post_say 只是让服务器把声音合成好，页面没有任何通道去取。

现在补了两条：

| 方向 | 怎么走 |
|---|---|
| **QQ → 网页** | 插件的 on_llm_response → POST /api/say → 服务器合成完顺手 push_inbox() → 页面每 800 ms 轮 GET /api/inbox?after=N → 页面自己播这段音频、写字幕、驱动口型 |
| **网页 → 她** | 页面右下角输入框 → POST /api/talk {text, state, history} → 走同一条 	hink()（AstrBot + livingmemory）→ 返回文字 → 页面 speak() |

几个实现细节：

- INBOX 是**进程内环形队列**（最近 40 条），重启 voice_server 就清空——够用，不落盘。
- 页面**第一次轮询只对齐游标**（window.__inboxInit），不然积压的几十条会被一口气念完。
- pumpInbox() 里每条都走 speak()，而不是自己操作 udioEl：合成结果已经在服务器缓存里，
  speak() 再打一次 /api/say 是 0.02 秒的缓存命中，但字幕/口型/表情/历史全都复用现成逻辑。
- **浏览器不弹**的修法：_open_browser() 依次试 explorer.exe URL → cmd /c start " URL →
  os.startfile，每步都写日志（[live_avatar] 打开通话页(explorer) -> ...）。
  计划任务起进程时 os.startfile 有时会被没有前台会话静默吞掉。
- **踩过的坑**：startRaf() 里还在用旧 2D 口型那套变量（mouthOpen / mouthWide / mouthPhase / 	），
  换真 Live2D 时这些声明被删了却没删用它的代码 → connect() 在 startRaf() 处抛
  mouthOpen is not defined，导致**音频、字幕、收件箱、聊天框全都不工作**，但页面看起来正常
  （HUD 是另一个定时器在刷）。报错只在 #gateMsg 里，而闸门已经淡出了，看不见。
  现在 connect() 的 catch 会把错误同时写进输入框 placeholder，一眼能看出来。

## 为什么说话有延迟，以及压到多少了

延迟是三段叠出来的，之前是串行等完：

| 段 | 之前 | 现在 |
|---|---|---|
| 她想说什么（AstrBot + 记忆） | 1.5 – 3.4 s | 1.5 – 3.4 s（LLM 本身，压不动） |
| TTS 出第一声 | **4.8 – 8 s**（整句合成完才给 url） | **2.4 – 3.3 s**（首包，流式） |
| 合计说完到听见 | **6 – 9 s** | **4 – 6.5 s**，且**同时**先抢一句「我在。」 |

做了四件事：

1. **流式合成**：POST /api/say/stream，TTS 按 max_text_tokens_per_segment=10 切小段，
   每算完一段就以裸 PCM（s16le / 22050 / mono，chunked）推出来。实测首包 **2.36 / 2.70 / 3.03 / 3.26 s**。
2. **前端边收边排**：speakStream() 把 PCM 灌进 AudioContext.createBuffer，
   按 
extTime 时间轴首尾相接排 BufferSource，全部接到 nalyser（所以嘴型和音量条照旧跟着动）。
3. **两条路都预热**：infer() 和 infer_generator() 是两个函数，得**各热一次** ——
   只热非流式的话，第一句流式仍要额外等 10 秒（实测首包 11.41 s，热完降到 2.4 s）。
4. **占位抢话**：GET /api/placeholder 返回一条启动时就合成好的短句（缓存命中 15 ms），
   安静超过 9 秒时他先听到「我在。」，真内容随后接上。
5. **让她话变短**：
um_predict 64 → 20，persona 改成「只说一句，十五个字左右」。
   音频短一半，合成时间跟着短一半。

**分句流水线（speakPipe）留着但基本不触发**：实测 IndexTTS 的 RTF ≈ 1.0–1.3，
短句有固定起步开销，硬切成多句反而更慢 —— 所以只有整段超过 22 字才切。

**还能更快的话只有一条路**：把 LLM 也做成流式（token 一出来就把前半句丢给 TTS），
理论上能再省 1–1.5 秒；再往下就是换更小的模型或用非克隆音色。

## 「电磁音」的真因（已修）

听起来像电流/爆音，实际是**整段削波**。诊断数据：

`
修前  s1.wav: 4.89s 峰值 1.000 削波采样 76698 大跳变 13571 处
修后  g1.wav: 4.17s 峰值 0.606 削波采样     0 大跳变   180 处
`

三处错叠在一起：

1. **流式 yield 的不是 ±1 波形**。IndexTTS 的 generator 交出来的是**已经放大到 int16 量级的 float**
   （实测首段峰值 **16291 / 18958 / 21689**）。我原来直接 clip(a,-1,1)*32767，
   等于把所有采样压成 ±1 —— 那就是满屏方波，听起来就是电磁音。
   修法：峰值 > 4 就先 /32768，再按首段定的固定增益缩放。
2. **段间硬接**。每段是独立的 buffer，首尾不归零就会咔哒。
   修法：每段首尾各 3ms 线性淡入淡出。
3. **增益按段自适应会导致段间音量跳**。修法：只用**首段**定增益，后面所有段共用。

另外顺手确认：_stream.wav（落盘那份）一直是对的，因为 save_pcm_wav 自己做了归一化 ——
只有 HTTP 推出去的那条路没做，所以文件没问题、网页有杂音。

## 延迟再压一轮

| 项 | 之前 | 现在 |
|---|---|---|
| 首包 | 2.4 – 3.3 s | **1.9 – 3.2 s** |
| 冷启动第一句 | **8.7 s** | 1.9 s（流式预热跑**两遍**才真的热） |
| 他感觉到没反应 | 3–4 s 空白 | **~0.15 s**（每次都先抢一声「嗯？」） |

两个关键点：

- **预热必须跑两遍**：第一遍只是建图/CUDA 上下文，第二遍才把 kernel 真正热起来。
  只跑一遍时重启后第一句仍要 8.7 秒（日志 流式预热完成 第1遍 / 第2遍）。
- **占位音改成每次都说**（原来只在安静 >9 秒时）：placeholderThen() 的触发条件
  从 idle > 9000 放宽到 idle > 2200。心理声学上有反应比更快出完整答案重要得多，
  真答案到了会先 udioEl.pause() 掐掉占位音，不会两条叠在一起。

**显存也是延迟的一部分**：ollama 的两个 llama-server 常驻会吃掉 2 GB 以上显存，
把 voice_server 挤到只剩 47 MiB 空闲，流式首包直接从 2.4 秒涨到 **17–30 秒**。
真出现突然变很慢，先 Get-Process llama-server | Stop-Process -Force。
