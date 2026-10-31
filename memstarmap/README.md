# 记忆星图 MEMORY STARMAP

长期记忆数据库（AstrBot 的 livingmemory 插件）可视化 —— 一个“记忆星空”3D 星图界面，附带对单条记忆的本地写操作（软删除 / 强化 / 改重要性）。

打开就能看到一团深空里的星云：1371 个记忆节点是星，5400 条关联是引力线。用户一眼就能看出“她（记忆库）记得什么、哪些记忆正在变淡”。

## 怎么启动

- 双击项目根目录的 `起星图.bat`（会用 `D:\sakana-py\python.exe` 起 `server.py`，监听 `127.0.0.1:8772`，自动打开浏览器）。
- 或手动：`D:\sakana-py\python.exe server.py` → 打开 `http://127.0.0.1:8772/`。

服务用 Python 3.12 **标准库**（http.server + sqlite3）实现，无任何第三方依赖，无外网请求。

首次打开前需先有 `data/graph.json`（由 `export_graph.py` 从 livingmemory 库导出）；若不存在，页面会提示“先跑 export_graph.py”。

## 视觉元素与含义

### 类型 `node.type`（决定颜色）

| 类型 | 颜色 | 含义 |
| --- | --- | --- |
| fact | 冷白 `#DEE5EE` | 客观事实 |
| topic | 暖米 `#CFAF72` | 话题主题 |
| person | 青绿 `#7DD6BE` | 人物（更亮、稍大一圈） |

### 新鲜度 `node.decay`（0~1，决定亮度 + 饱和度）

- `1.0` = 刚记住，颜色完整、亮度高、饱和高，是“明亮的星”。
- 低值 = 快要忘了 → 颜色向灰色过渡、变暗、变灰，几乎沉进背景。
- 用亮度 + 饱和度双通道表达，**不**用红绿灯。

### 重要性 `node.imp` / `node.deg`（决定星大小）

- 大小公式：`0.6 + log2(1 + deg) * 0.5`，再乘以 `imp` 的幅度修正（`0.85 + 0.3*imp`）与类型大小系数。
- person 再乘 `1.18`（更亮、稍大一圈）。

### 深度（近大远小、远处更暗更细）

- Canvas2D 透视投影：星星按相机距离分层，近处放大、远处变小、变暗。
- 边（引力线）按两端最小深度分桶，远处几乎看不见、细得几乎隐形，近处才显形。

### 交互

- **鼠标拖拽**旋转 / **滚轮**缩放 / **双击**复位。
- **悬停**：星星放大（×1.55）+ tooltip 显示 `value` 前 40 字 + 类型/衰减。
- **点击**：右侧滑出详情面板（类型 / 度数 / 创建时间 / 衰减 / 关联原子数），并列出该节点关联的 atom 原文（最多 8 条，按 importance 降序）。
- **顶部搜索**：输入关键词过滤/高亮匹配节点（加虚线描边），`Enter` 聚焦到第一个匹配。
- **衰减阈值滑杆**（默认 0.50）：拖动后，`decay` 低于阈值的节点整体变暗/隐藏。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 静态文件（index.html / app.js / style.css / data/graph.json） |
| GET | `/api/graph` | 返回 `data/graph.json` 内容 |
| GET | `/api/atoms?node=<节点id>&limit=8` | 该节点关联 atom 列表（content LIKE `value[:12]`，importance 降序，最多 limit 条），带 atom 真实 `id`，含 `left_days` |
| POST | `/api/atom/forget` | `{"id": 123}` → 软删除 |
| POST | `/api/atom/reinforce` | `{"id": 123}` → 强化，延长 TTL |
| POST | `/api/atom/importance` | `{"id": 123, "value": 0.6}` → 改重要性并重算 TTL |
| GET | `/api/ops` | 最近 50 条操作日志 |
| GET | `/api/health` | `{"ok":true,"atoms":767,"backups":N}` |

## 三个写操作的语义（严格按 livingmemory 插件约定）

每次写之前自动备份：`sqlite3.connect(DB).execute("VACUUM INTO ?", (备份路径,))` → 备份到
`memstarmap\backups\livingmemory-YYYYMMDD-HHMMSS.db`，最多保留 20 份，超了删最旧。

写用短事务：`conn.execute("BEGIN IMMEDIATE")` → 改 → `commit()`，连接 `busy_timeout=5000`。

每笔操作追加一行 JSON 到 `memstarmap\ops.log`（时间 / 动作 / atom id / 改前值 / 改后值）。

### 1. forget（软删除）

```sql
UPDATE memory_atoms SET status='forgotten' WHERE id=?
```

只改 status。**不要动 FTS 表、不要 DELETE**。插件检索条件是 `status='active' AND expires_at > now`，所以改 status 就够了，零风险。

### 2. reinforce（强化，延长寿命）

先查出现值 `atom_type, importance, confidence, reinforcement_count`，然后：

```python
BASE = {'episodic':7,'planned':2,'factual':180,'relational':90,'preference':60,'unknown':30}
base = BASE.get(atom_type, 30)
new_reinf = reinforcement_count + 1
ttl = max(1.0, base * (0.5 + importance) * (1 + min(0.5, new_reinf * 0.1)))
expires = time.time() + ttl * 86400
```

```sql
UPDATE memory_atoms
SET reinforcement_count=?, ttl_days=?, expires_at=?,
    last_reinforced_at=?, confidence=MIN(1.0, confidence+0.05)
WHERE id=?
```

### 3. importance（改重要性，**必须连带重算 TTL**）

```python
new_imp = clamp(value, 0.01, 1.0)
ttl = max(1.0, base * (0.5 + new_imp) * (1 + min(0.5, reinf * 0.1)))
expires = time.time() + ttl * 86400
```

```sql
UPDATE memory_atoms SET importance=?, ttl_days=?, expires_at=? WHERE id=?
```

（改了 importance 不重算 TTL 会自相矛盾，这是必须的。）

## 备份策略

- 每次写操作前自动 `VACUUM INTO` 备份到 `backups/livingmemory-YYYYMMDD-HHMMSS.db`。
- 最多保留 20 份，超了删最旧。

## 已知限制

- 未做 WebGL 渲染（Canvas2D 已满足 1371 节点 / 5400 边的 40fps 目标）。
- 未做所有节点的常驻文字标签（仅悬停 tooltip + 选中详情）。
- atom 与节点之间没有直接外键，按 `value[:12]` 前缀 + LIKE 匹配（成本可接受）。
- 前端所有写操作都来自本地同源 API，无 CORS，无外网。

## 配色

- 底 `#0B0F15`，面板 `rgba(11,15,21,.92)` + 轻微模糊
- 主文字 `#C7C8CB`，次要 `#8A8F96`，更弱 `#5B626B`
- 高亮/数值暖色 `#D9C49A`
- 等宽 `ui-monospace,"Cascadia Mono",Consolas,monospace`；中文 `"Microsoft YaHei"`
- 小标题 10-11px 全大写 `letter-spacing:.14em` 颜色 `#5B626B`
- 不要大圆角卡片、不要发光科技按钮，要像仪器面板
