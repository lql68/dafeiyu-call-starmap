# 让 AstrBot 的 comfyui 插件真正跑起来

## 一句话

原来「插件无法使用 ComfyUI」有两个独立原因，都补掉了：

1. **ComfyUI 里没有 `Simple String` 节点** —— 插件只会把提示词注入到 `class_type == "Simple String"` 的节点里，而你的 ComfyUI `customNodes: []`，一个自定义节点都没装，所以就算有工作流也没地方塞提示词。
2. **没有 API 格式的工作流** —— 插件只读 API 格式（`文件 → 导出(API)`），你手上那两份是 UI 格式。

## 具体做了什么

### 1. 补一个零依赖的 Simple String 节点

`ComfyUI\custom_nodes\astrbot_simple_string\__init__.py`

官方推荐装 [CG Use Everywhere](https://github.com/chrisgoringe/cg-use-everywhere)，但那个包很重。这里写了 20 行的等价实现，只注册一个类名恰好为 `"Simple String"` 的节点，`INPUT_TYPES` 里有一个 `text` 字符串输入 —— 正好是插件要找的形状。

启动日志会看到：`0.0 seconds: ...custom_nodes\astrbot_simple_string`。

### 2. 两份工作流转成 API 格式

转换脚本 `ai-live\comfy\ui2api.py`（UI 格式 → API 格式，并把正面提示词换成 Simple String）：

| 源文件（UI 格式） | 插件工作流（API 格式） | 节点数 |
|---|---|---|
| `D:\Comfy-Desktop\wai-illustrious-default.json` | `astrbot_plugin_comfyui\workflows\WAI插画+文本1.json` | 8 |
| `D:\Comfy-Desktop\wai-illustrious-hires-fix.json` | `astrbot_plugin_comfyui\workflows\WAI插画高清+文本1.json` | 10 |

- 正面 `CLIPTextEncode` 的 `text` 改成连到 `Simple String`（id 100），负面提示词保持写死 —— **不让 LLM 碰负面词**。
- 文件名带 `+文本1`，这是插件的命名规范：`parse_workflow_filename()` 靠它判断要注入几个文本。
- 同时把 UI 格式原件拷进了 `ComfyUI\user\default\workflows\`（`WAI插画.json` / `WAI插画高清.json`），这样在 ComfyUI 界面里能直接打开看。

### 3. 工作流说明

`astrbot_plugin_comfyui\workflow_meta.json` —— `descriptions` 给 LLM 看（决定什么时候用哪个），`text_slots` 告诉它那个槽位该写什么。

## 验过的证据

- `GET /object_info/Simple String` 返回了节点定义 ✅
- 用插件自己的代码跑注入（`ComfyUIWorkflow._update_text_nodes`）：
  `WAI插画+文本1.json | 解析: {'name': 'WAI插画', 'texts': 1, ...} | 替换: 1`
- 真跑一次文生图：`POST /prompt` → 30.2s → `wai_illustrious_00001_.png`（1024×1024）
- 真跑一次高清：50.3s → `wai_illustrious_hires_00001_.png`（1536×1536）

## 启动 ComfyUI 注意

`extra_model_paths.yaml`（新建在 ComfyUI 根目录）把模型指到 Comfy Desktop 的共享目录 `D:\Comfy-Desktop\ComfyUI-Shared\models`。

- 命令行启动要带：`python main.py --port 8188 --extra-model-paths-config extra_model_paths.yaml`
- **不带这个参数的话 `ckpt_name` 列表是空的**，`/prompt` 会直接 400（`Value not in list`），这就是我第一次提交失败的原因。
- 用 Comfy Desktop 自己打开时，它走 `D:\Comfy-Desktop\model-paths.yaml`，同样没问题。

## 插件侧不用重启

`main.py` 里 `_get_workflow_dir()` 每次调用都重新 `glob("*.json")`，**没有缓存**，所以新增工作流 AstrBot 那边立刻能看到。

管理页（如果开着）：`http://127.0.0.1:6187`。
