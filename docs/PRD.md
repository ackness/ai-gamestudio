# AI GameStudio — 产品需求文档 (PRD)

> LLM-Native 低代码 RPG 游戏编辑器与运行平台

---

## 1. 产品愿景

AI GameStudio 是一个基于 Web 的**低代码 RPG 游戏编辑器与运行平台**。用户无需编写代码，仅通过编排世界观文档（Markdown）和配置插件，即可借助大语言模型（LLM）的能力**实时生成并游玩 RPG 游戏内容**。

核心理念：**LLM-Native RPG Maker** —— 将大模型深度融入游戏内容的生成、运行与演化全过程，突破传统 RPG Maker 依赖硬编码逻辑的局限。

### 灵感来源

| 项目 | 参考点 |
|------|--------|
| [SillyTavern](https://github.com/SillyTavern/SillyTavern) | 将 LLM 接入角色扮演/互动叙事的思路；事件系统与 Prompt 注入架构 |
| [RPGGO](https://rpggo.ai) | 多 Bot 协作的 RPG 架构；DM（Dungeon Master）协调者模式；游戏状态机 |
| [Agent Skills](https://agentskills.io) | 插件格式设计（SKILL.md → PLUGIN.md）；渐进式加载；文档驱动 |

### 竞品分析

| 产品 | 定位 | 与 AI GameStudio 的差异 |
|------|------|------------------------|
| RPG Maker MZ | 传统 RPG 编辑器 | 需要编程，无 LLM 集成，逻辑硬编码 |
| RPGGO | AI 文字 RPG 平台 | 仅文字交互，无可视化编辑器，插件不可扩展 |
| SillyTavern | LLM 角色扮演前端 | 聊天导向而非游戏导向，无游戏机制（技能/背包/时间等） |
| AI Dungeon | AI 生成式冒险 | 黑盒生成，用户无法自定义世界规则和游戏机制 |

---

## 2. 目标用户

| 用户画像 | 描述 |
|---------|------|
| 非程序员游戏设计者 | 不会或不想写代码，但有丰富的世界观创意和叙事想法 |
| 世界观作者 / 小说作者 | 希望将自己的世界观转化为可交互的游戏体验 |
| RPG 爱好者 | 想快速原型化和测试自己的 RPG 创意 |

---

## 3. 核心概念模型

```
┌─────────────────────────────────────────────────────────────┐
│                        游戏项目                               │
│                                                              │
│  ┌─────────────────────────────────┐                        │
│  │         世界观文档 (Markdown)     │  ← 游戏的"源代码"      │
│  │  - 背景设定、规则、种族、地理     │                        │
│  │  - 核心叙事框架                   │                        │
│  └────────────────┬────────────────┘                        │
│                   │                                          │
│                   ▼                                          │
│  ┌─────────────────────────────────┐                        │
│  │   插件系统 (manifest + 手册)     │  ← 扩展游戏能力        │
│  │                                  │                        │
│  │  全局插件        游戏性插件       │                        │
│  │  ├─ database     ├─ character    │                        │
│  │  ├─ memory       ├─ skill-check  │                        │
│  │  ├─ archive      ├─ combat       │                        │
│  │  └─ core-blocks  └─ inventory... │                        │
│  └────────────────┬────────────────┘                        │
│                   │                                          │
│                   ▼                                          │
│  ┌─────────────────────────────────┐                        │
│  │       LLM 引擎 (多模型接入)      │  ← 内容生成与裁决      │
│  │  - 游戏主持人（DM）模式          │                        │
│  │  - NPC 独立人格驱动              │                        │
│  │  - 事件/技能动态裁决             │                        │
│  └────────────────┬────────────────┘                        │
│                   │                                          │
│                   ▼                                          │
│  ┌─────────────────────────────────┐                        │
│  │       游戏运行时 / 游玩界面       │  ← 设计即游玩          │
│  └─────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 核心功能

### 4.1 世界观编辑器

- 用户通过 **Markdown 文档** 描述游戏世界观（背景设定、规则、种族、地理等）
- 支持 frontmatter 元数据编辑（name/description/genre/tags/plugins）与 `.md` 导出
- 支持 AI 流式生成与 AI 指令修订（search/replace 轻量补丁 + 修改预览）
- 支持与游戏运行时并排编辑（编辑区/游戏区/状态区）与多 Tab 工作流（世界文档/初始提示/模型/小说）
- 世界观文档即游戏的"源代码"

### 4.2 插件系统

> 详见 [PLUGIN-SPEC.md](./PLUGIN-SPEC.md)

插件采用 **manifest.json + PLUGIN.md** 双文件格式（V2 规范），以机器可读元数据 + LLM 可读运行手册共同定义游戏能力。

核心设计原则：
- **双事实源分层**：`manifest.json` 负责运行时契约，`PLUGIN.md` 负责 LLM 提示与操作手册
- **渐进式加载**：启动时仅加载插件名称和描述，激活时才加载完整内容
- **LLM 协作**：插件可声明 LLM 交互模式，将世界状态作为上下文传入模型

插件分类：
- **全局插件**：控制世界级别状态（`core-blocks`、`database`、`archive`、`memory`）
- **游戏性插件**：扩展玩法机制（`character`、`choices`、`auto-guide`、`dice-roll`、`skill-check`、`combat`、`inventory`、`quest`、`faction`、`relationship`、`status-effect`、`codex`、`story-image`）

### 4.3 LLM 引擎

参考 RPGGO 的多 Bot 架构，引入 **DM（Dungeon Master / 游戏主持人）** 模式：

```
                    ┌─────────────┐
                    │   DM Agent   │  ← 全局协调者
                    │  (主持人 AI)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ NPC Bot  │ │ NPC Bot  │ │ NPC Bot  │  ← 独立人格
        │ (角色 A)  │ │ (角色 B)  │ │ (角色 C)  │
        └──────────┘ └──────────┘ └──────────┘
```

- **DM Agent**：全局协调者，负责叙事推进、事件裁决、规则执行
- **NPC Bot**：每个重要 NPC 由独立的 LLM 会话驱动，拥有自己的人格和记忆
- 接入多种大模型 API（OpenAI、Claude、本地模型等）
- 插件可将世界状态（背包、属性、世界观）作为上下文传入 LLM

消息流水线（参考 SillyTavern 的 Prompt 组装思路）：

```
用户输入
  │
  ▼
┌──────────────────────────────┐
│ Prompt 组装器                 │
│                              │
│  [系统指令]                   │  ← 世界观文档 + 全局插件注入
│  [角色设定]                   │  ← 角色插件注入
│  [世界状态]                   │  ← 数据库插件提供当前状态
│  [记忆上下文]                 │  ← 记忆插件注入相关记忆
│  [对话历史]                   │  ← 最近 N 条消息
│  [当前插件上下文]              │  ← 激活的游戏性插件注入
│  [用户消息]                   │
└──────────────┬───────────────┘
               │
               ▼
         ┌───────────┐
         │  LLM API  │
         └─────┬─────┘
               │
               ▼
┌──────────────────────────────┐
│ 响应处理器                    │
│  - 解析结构化输出              │
│  - 触发插件副作用              │  ← 更新数据库、角色状态等
│  - 渲染到游戏界面              │
└──────────────────────────────┘
```

### 4.4 游戏运行时

- 在平台内直接游玩和测试
- 设计与游玩无缝切换
- 消息类型区分（参考 RPGGO）：
  - **玩家消息**：用户输入的行动/对话
  - **NPC 消息**：由 NPC Bot 生成的角色对话和行为
  - **系统消息**：游戏状态变化、事件通知、环境描述
- 游戏状态管理：场景切换、目标追踪、结局判定

### 4.5 会话生命周期

游戏会话（GameSession）具有明确的阶段流转：

```
  init --> character_creation --> playing --> ended
   |                                |
   +--- (skip if character exists) -+
```

| 阶段 | 描述 |
|------|------|
| `init` | 会话刚创建，系统发送开场白 |
| `character_creation` | 引导玩家创建角色（通过对话或表单） |
| `playing` | 正常游戏阶段，玩家与世界交互 |
| `ended` | 游戏结束或会话关闭 |

### 4.6 场景管理

场景（Scene）是游戏中的空间单位，表示玩家当前所处的位置或环境。

功能：
- 每个会话有一个**当前场景**（`is_current = true`）
- 场景切换时，DM 生成 `json:scene_update` 块描述新场景
- 场景可关联 NPC（通过 SceneNPC），表示哪些 NPC 出现在当前场景
- 场景信息注入到 Prompt 中，让 LLM 了解当前环境

### 4.7 事件系统

事件（GameEvent）跟踪游戏中发生的重要事情，具有完整的生命周期：

```
active --> evolved --> resolved --> ended
  |                      |
  +--- ended (aborted) --+
```

事件类型：
- **quest** — 任务/目标
- **combat** — 战斗遭遇
- **social** — NPC 互动、关系变化
- **world** — 世界级事件（天气、政治）
- **system** — 引擎生成的系统事件

事件特性：
- 支持父子关系（`parent_event_id`），构成事件链
- 支持来源追踪（`source`）：dm / plugin:<name> / system
- 支持可见性控制（`visibility`）：known / hidden
- 活跃事件注入到 Prompt 中，影响 LLM 叙事

### 4.8 Block 协议

LLM 响应中的结构化数据通过 `` ```json:<type> `` 代码块传递。这是 LLM 与游戏引擎之间的核心通信机制。

处理流水线：
1. **插件模板** 指导 LLM 输出特定类型的 block
2. **Block Parser** 从 LLM 响应中提取所有 `json:xxx` 块
3. **Block Handler** 在后端处理各类型的 block（如写入数据库）
4. **Block Renderer** 在前端渲染 block 对应的 UI 组件

支持的 Block 类型：

| 类型 | 后端处理 | 前端渲染 | 说明 |
|------|---------|---------|------|
| `state_update` | 更新数据库 | -- | 世界状态变更 |
| `character_sheet` | 更新角色数据 | 角色卡片 UI | 角色信息展示/编辑 |
| `scene_update` | 创建/更新场景 | 场景切换通知 | 场景变更 |
| `event` | 创建 GameEvent | 事件通知 | 游戏事件 |
| `notification` | 透传 | 通知卡片 UI | 系统提示/警告 |
| `choices` | -- | 选项按钮 | 玩家选择 |
| `guide` | 透传 | 建议行动 UI | 自动行动建议 |
| `story_image` | 触发图片生成并落库 | 图片卡片 UI | 场景/消息配图 |
| `dice_result` | 声明式动作（存储+事件） | 通用卡片 UI | 检定结果 |
| `skill_check_result` | 声明式动作（存储+事件） | 自定义卡片 UI | 技能检定结果 |
| `combat_start` | 声明式动作（存储+事件） | 自定义卡片 UI | 战斗开始 |
| `combat_round` | 声明式动作（存储） | 自定义卡片 UI | 战斗回合结算 |
| `combat_end` | 声明式动作（存储+事件） | 自定义卡片 UI | 战斗结束 |
| `loot` | 声明式动作（存储+事件） | 自定义卡片 UI | 战利品掉落 |
| `quest_update` | 声明式动作（存储+事件） | 自定义卡片 UI | 任务进度更新 |
| `reputation_change` | 声明式动作（存储+事件） | 自定义卡片 UI | 阵营声望变化 |
| `relationship_change` | 声明式动作（存储+事件） | 自定义卡片 UI | NPC 关系变化 |
| `status_effect` | 声明式动作（存储+事件） | 自定义卡片 UI | 状态效果变化 |
| `codex_entry` | 声明式动作（存储+事件） | 自定义卡片 UI | 图鉴条目更新 |
| `plugin_use` | CapabilityExecutor 执行 | 结果 block 渲染 | 插件能力调用协议 |

### 4.9 小说生成功能

将会话中的世界设定、角色、事件与对话记录编织为章节小说：

- 输入：当前会话 `world_doc`、消息历史、角色数据、事件时间线
- 生成流程：先生成章节大纲，再逐章流式生成正文
- 传输协议：后端通过 NDJSON 事件流返回 `outline` / `chapter_chunk` / `chapter` / `done`
- 前端能力：章节侧栏预览、生成中断、导出 Markdown

---

## 5. 内置插件清单（当前实现）

当前内置插件共 **17 个**，分为全局插件 4 个与游戏性插件 13 个。

### 5.1 全局插件（4）

| 插件 | 必需/默认 | 主要职责 |
|------|-----------|----------|
| `core-blocks` | 必需 | 定义核心 `json:xxx` Block（状态/角色卡/场景/事件/通知） |
| `database` | 必需 | 提供持久化世界状态上下文与通用状态读写 |
| `archive` | 必需 | 长会话摘要与版本化快照存档 |
| `memory` | 默认启用 | 记忆提取与 Prompt memory 位置注入 |

### 5.2 游戏性插件（13）

| 插件 | 关键 Block | 能力调用（`plugin_use`） |
|------|------------|--------------------------|
| `character` | （以状态注入为主） | — |
| `choices` | `choices` | — |
| `auto-guide` | `guide` | —（`supersedes: choices`） |
| `dice-roll` | `dice_result` | `dice.roll` |
| `skill-check` | `skill_check` / `skill_check_result` | `skill_check.resolve` |
| `combat` | `combat_start` / `combat_round` / `combat_end` / `combat_action` | `combat.resolve_action` |
| `inventory` | `item_update` / `loot` | `inventory.use_item` |
| `quest` | `quest_update` | — |
| `faction` | `reputation_change` | — |
| `relationship` | `relationship_change` | — |
| `status-effect` | `status_effect` | `status_effect.tick` |
| `codex` | `codex_entry` | — |
| `story-image` | `story_image` | —（默认启用） |

### 5.3 运行时约束

- `core-blocks` / `database` / `archive` / `character` 为必需插件。
- `memory` / `auto-guide` / `story-image` 默认启用，其余按项目按需启用。
- `auto-guide` 启用时可替代 `choices` 的行动建议输出。
- 能力调用统一走 `json:plugin_use`，由后端 `CapabilityExecutor` + `ScriptRunner` 执行并审计。

---

## 6. 技术架构

### 6.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                       前端 (Web SPA)                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │  世界观编辑器  │  │  插件配置面板  │  │  游戏运行界面    │    │
│  │  (Markdown)   │  │ (manifest+手册) │ │  (对话/交互)   │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                 游戏状态面板                            │   │
│  │  角色状态 | 背包 | 技能 | 世界时间 | 事件日志           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────┘
                              │ WebSocket / REST API
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        后端服务                               │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │  插件引擎      │  │  LLM 网关     │  │  Prompt 组装器  │    │
│  │  (调度/生命    │  │  (多模型路由)  │  │  (上下文管理)   │    │
│  │   周期管理)    │  │              │  │                │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │  脚本沙箱      │  │  定时任务调度  │  │  游戏状态管理   │    │
│  │  (Py/JS)      │  │  (Cron)      │  │  (状态机)      │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        数据层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │  数据库        │  │  文件存储      │  │  缓存           │    │
│  │  (SQLite/PG)  │  │  (世界观/插件) │  │  (会话/记忆)    │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 技术选型

> 详见 [TECH-STACK.md](./TECH-STACK.md) 和 [ARCHITECTURE.md](./ARCHITECTURE.md)

| 层级 | 方案 |
|------|------|
| 前端框架 | React 19 + Vite (SPA) |
| UI 样式 | Tailwind CSS v4 + shadcn/ui（Radix primitives） |
| 状态管理 | Zustand |
| Markdown 编辑器 | 原生 textarea + frontmatter 元数据面板 + AI 修订预览 |
| 浏览器存储 | IndexedDB（离线 / Vercel 模式） |
| 后端框架 | Python FastAPI |
| ORM | SQLModel (Pydantic + SQLAlchemy) |
| 数据库 | SQLite（本地）/ PostgreSQL（生产） |
| LLM 接入 | LiteLLM (100+ provider) |
| 模板引擎 | Jinja2 |
| 实时通信 | WebSocket + HTTP fallback（Vercel 用） |
| 插件脚本 | Python subprocess（stdin/stdout JSON） |
| 审计日志 | JSON-lines append-only 文件 |

---

## 7. 核心差异化优势

| 对比维度 | 传统 RPG Maker | AI GameStudio |
|---------|---------------|---------------|
| 内容生成 | 手动编写所有剧情和对话 | LLM 实时生成，无限内容 |
| 技能系统 | 硬编码固定效果 | LLM 情境感知，动态裁决 |
| 随机事件 | 预设事件池 | LLM 即时创作，独一无二 |
| NPC 交互 | 预设对话树 | LLM 驱动自然对话，独立人格 |
| 扩展方式 | 编写代码/脚本 | PLUGIN.md 文档 + 插件配置 |
| 上手门槛 | 需要编程知识 | 零代码，会写文档即可 |
| 灵活性 | 受限于引擎预设 | 通过插件无限扩展 |

---

## 8. 已实现功能（当前状态）

### 核心引擎
- [x] Web 端世界观 Markdown 编辑器（模板选择、流式 AI 生成、search/replace AI 修订、frontmatter 元数据编辑、导出）
- [x] 游戏对话/交互界面（流式输出、Block 渲染、会话管理）
- [x] 小说生成面板（会话素材→章节大纲→逐章流式正文，支持中断与导出）
- [x] LiteLLM 接入（100+ 模型供应商，WebSocket + HTTP 双通道）
- [x] Prompt 组装器（6 位置注入，Jinja2 模板）
- [x] 插件系统（manifest.json V2 + PLUGIN.md V1 回退，依赖拓扑排序）
- [x] Block 协议（提取、校验、分发、前端渲染注册系统）
- [x] 模型设置增强（预设模型高亮、连接测试 `/api/llm/test`、按项目本地配置）
- [x] 前端 UI 体系重构（shadcn/ui + Radix + 统一设计 Token）

### 内置插件（17 个）
- [x] core-blocks（状态同步、角色卡、场景、事件、通知）
- [x] database（持久状态上下文）
- [x] archive（长会话摘要 + 版本化快照）
- [x] memory（记忆注入）
- [x] character（玩家/NPC 状态管理）
- [x] choices（交互选项 Block）
- [x] auto-guide（AI 推荐行动）
- [x] dice-roll（骰子 Block + 脚本执行）
- [x] skill-check（技能检定请求/结果 + 脚本执行）
- [x] combat（战斗开始/回合/结束 + 动作解析）
- [x] inventory（物品变更/战利品 + 使用物品能力）
- [x] quest（任务生命周期更新）
- [x] faction（阵营声望变化）
- [x] relationship（关系变化追踪）
- [x] status-effect（Buff/Debuff 生命周期）
- [x] codex（图鉴/百科条目记录）
- [x] story-image（剧情图片生成 + 连续性）

### 基础设施
- [x] `json:plugin_use` 能力调用协议（CapabilityExecutor）
- [x] Python 脚本执行（ScriptRunner，stdin/stdout JSON）
- [x] 审计日志（AuditLogger，JSON-lines）
- [x] 插件导入/验证/安装 API
- [x] 运行时设置（按插件 + 按 project/session 范围）
- [x] 多语言界面（中/英，含插件设置 i18n）
- [x] 灵活存储（SQLite 本地 / IndexedDB 浏览器离线，自动探测）
- [x] Vercel 无服务器部署支持

### 后续规划
- [ ] `hooks` 生命周期脚本执行框架
- [ ] JavaScript 脚本支持
- [ ] 插件导出（zip/tarball）
- [ ] 插件市场 / 社区分享
- [ ] 多人协作编辑
- [ ] 游戏发布与分享

---

## 9. 术语表

| 术语 | 说明 |
|------|------|
| 世界观文档 | 用 Markdown 编写的游戏世界设定，是游戏的"源代码" |
| manifest.json + PLUGIN.md | V2 插件双文件：manifest 定义运行时契约，PLUGIN.md 定义 LLM 运行手册 |
| 全局插件 | 控制整个游戏世界运行规则的插件（如数据库、记忆） |
| 游戏性插件 | 扩展具体玩法机制的插件（如角色、战斗、任务、背包、关系） |
| DM Agent | Dungeon Master，全局游戏主持人 AI，负责叙事协调和规则裁决 |
| NPC Bot | 由独立 LLM 会话驱动的 NPC，拥有自己的人格和记忆 |
| Prompt 组装器 | 将世界观、插件上下文、记忆等组装为 LLM 请求的核心组件 |
| LLM 裁决 | 将游戏状态传入大模型，由模型判定事件/技能/对话的结果 |
| 插件调度器 | 负责根据事件类型将请求路由到对应插件的核心组件 |
| json:xxx Block | LLM 响应中的结构化数据块，用 `` ```json:<type> `` 围栏标记 |
| Block Handler | 后端处理 json:xxx 块的处理器（如 state_update 写入数据库） |
| Block Renderer | 前端渲染 json:xxx 块的 React 组件（如 ChoicesRenderer） |
| Scene（场景） | 游戏中的空间单位，表示玩家当前所处的位置或环境 |
| GameEvent（事件） | 游戏中发生的重要事件，具有 active/evolved/resolved/ended 生命周期 |
| Session Phase（会话阶段） | 游戏会话的当前阶段：init / character_creation / playing / ended |

---

## 10. 相关资源

- [架构文档](./ARCHITECTURE.md) — 技术架构详细说明
- [插件规范文档](./PLUGIN-SPEC.md) — manifest.json + PLUGIN.md 完整定义
- [技术栈文档](./TECH-STACK.md) — 技术选型与开发环境
- [Agent Skills 规范](https://agentskills.io/specification) — 插件格式的灵感来源
- [SillyTavern](https://github.com/SillyTavern/SillyTavern) — 事件系统与扩展架构参考
- [RPGGO](https://rpggo.ai) — 多 Bot RPG 架构参考

---

*文档版本：v0.7 | 更新日期：2026-02-22*
