# AI GameStudio Plugin Spec v3.0

> 本文是 V3 实现规范（runtime contract）。插件开发者按本文可直接编写插件，无需了解后端代码。
>
> 核心变化：V3 采用 **Plugin Agent + 并行执行** 架构。主 LLM 只输出纯叙事；
> Plugin Agent 为每个启用插件启动独立的 LLM 调用（并行执行），通过 function calling 操作游戏数据、输出结构化 block。
>
> 架构蓝图：`docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md`（设计原则、执行流程、组件架构）。

---

## 1. 概述

### 1.1 架构模型

```
用户消息 → 主 LLM（纯叙事）→ 流式输出故事
         → Plugin Agent（并行执行）
              ├─ 插件 A 的 LLM 调用（独立，GameDB autocommit=False）
              ├─ 插件 B 的 LLM 调用（独立，GameDB autocommit=False）
              └─ 插件 C 的 LLM 调用（独立，GameDB autocommit=False）
              每个插件的 LLM 调用可使用（7 个工具）：
              ├─ update_and_emit()  → 批量 DB 写入 + 输出 blocks + 追加日志
              ├─ emit_block()       → 纯展示 block（无需 DB）
              ├─ db_read()          → 读取游戏数据
              ├─ db_log_append()    → 追加日志
              ├─ db_log_query()     → 查询日志
              ├─ db_graph_add()     → 添加关系边
              └─ execute_script()   → 执行插件脚本
```

**直接注入**：V3 并行模式下，每个插件的 PLUGIN.md 内容作为系统提示词预加载到其独立的 LLM 调用中（直接从 Level 2 开始），游戏状态快照作为用户消息提供。
无需 `list_plugins()` 或 `load_plugin()` 工具（已移除）。
每个插件的 LLM 调用独立执行 `update_and_emit()`、`emit_block()`、`execute_script()` 或 `db_*` 工具操作。

### 1.2 插件开发者须知

- **插件 = 一个文件夹**。无需编写 Python 后端代码。
- **PLUGIN.md** 是 Plugin Agent 的"运行手册"——写清楚何时触发、怎么操作、输出什么 block。
- **manifest.json** 是运行时的"事实源"——声明依赖、权限、block schema、capabilities、i18n。
- 如果需要计算逻辑（如骰子、战斗判定），放在 `scripts/` 中，Plugin Agent 会通过 `execute_script()` 调用。
- 所有自带插件**必须提供中文和英文两种翻译**（`i18n.zh` + `i18n.en`）。

---

## 2. 插件包结构

### 2.1 Builtin 插件（最小 2 文件）

```text
my-plugin/
├── PLUGIN.md           # Plugin Agent 运行手册（必需）
├── manifest.json       # 运行时事实源（必需）
├── prompts/            # Jinja2 模板（可选）
│   └── *.md
├── scripts/            # 可执行脚本（可选）
│   └── *.py
└── references/         # 参考文档（可选）
```

### 2.2 External 插件（完整 4 文件）

```text
my-plugin/
├── PLUGIN.md           # Plugin Agent 运行手册（必需）
├── manifest.json       # 运行时事实源（必需）
├── README.md           # 人类文档（必需）
├── schemas/            # 结构化契约（必需）
│   ├── index.yaml      # 索引文件（推荐）
│   └── blocks/
│       └── *.yaml
├── prompts/
│   └── *.md
├── scripts/
│   └── *.py
└── references/
```

### 2.3 分组目录

插件可以放在分组目录中。分组目录下必须有 `group.json` 文件：

```text
plugins/
├── core/                   # 分组目录
│   ├── group.json          # 分组标识文件
│   ├── database/           # 插件
│   ├── state/
│   ├── event/
│   └── memory/
├── narrative/
│   ├── group.json
│   ├── guide/
│   ├── codex/
│   └── image/
└── rpg-mechanics/
    ├── group.json
    ├── combat/
    ├── inventory/
    └── social/
```

发现逻辑：扫描 `plugins/` 的直接子目录，有 `PLUGIN.md` 的是扁平插件，有 `group.json` 的是分组目录（递归扫描其子目录中有 `PLUGIN.md` 的插件）。

### 2.4 职责分离

| 文件 | 受众 | 职责 |
|------|------|------|
| `PLUGIN.md` | Plugin Agent（LLM） | 运行手册：触发条件、执行步骤、输出要求、降级策略 |
| `manifest.json` | 运行时引擎 | 唯一事实源：依赖、权限、能力、blocks、events、storage、i18n |
| `README.md` | 开发者 | 安装、调试、测试说明 |
| `schemas/` | 运行时 + 前端 | block/ui schema 契约 |

---

## 3. `manifest.json` 完整字段定义

### 3.1 示例

```json
{
  "schema_version": "2.0",
  "name": "combat",
  "version": "0.1.0",
  "type": "gameplay",
  "required": false,
  "default_enabled": false,
  "supersedes": ["skill-check", "dice-roll", "status-effect"],
  "description": "Unified combat system: turn-based combat, dice rolls, skill checks, and status effects.",
  "dependencies": ["state"],

  "prompt": {
    "position": "pre-response",
    "priority": 70,
    "template": "prompts/combat-instruction.md"
  },

  "capabilities": {
    "dice.roll": {
      "description": "解析骰子表达式（如 2d6+3）并执行随机掷骰",
      "implementation": {
        "type": "script",
        "script": "scripts/roll.py",
        "timeout_ms": 5000
      },
      "result_block_type": "dice_result"
    }
  },

  "blocks": {
    "dice_result": {
      "schema": {
        "type": "object",
        "properties": {
          "dice": { "type": "string" },
          "result": { "type": "integer" },
          "success": { "type": "boolean" },
          "description": { "type": "string" }
        },
        "required": ["dice", "result"]
      },
      "handler": {
        "actions": [
          { "type": "storage_write", "key": "last-roll" },
          { "type": "emit_event", "event": "dice-rolled" }
        ]
      },
      "ui": {
        "component": "card",
        "title": "🎲 {{ dice }}"
      },
      "requires_response": false
    }
  },

  "events": {
    "emit": ["dice-rolled", "combat-started", "combat-ended"],
    "listen": []
  },

  "storage": {
    "keys": ["last-roll", "combat-state"]
  },

  "permissions": {
    "network": false,
    "filesystem_scope": ["plugin", "data"],
    "script_languages": ["python"]
  },

  "extensions": {},

  "i18n": {
    "en": { "name": "Combat", "description": "Turn-based combat, dice rolls, skill checks, and status effects." },
    "zh": { "name": "战斗系统", "description": "回合制战斗、骰子判定、技能检定与状态效果。" }
  }
}
```

### 3.2 字段定义

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `schema_version` | string | 是 | 固定为 `"2.0"` |
| `name` | string | 是 | 插件唯一 ID，必须与目录名一致，格式：小写字母/数字/连字符 |
| `version` | string | 是 | 插件版本（建议 semver） |
| `type` | enum | 是 | `"global"` 或 `"gameplay"` |
| `required` | boolean | 是 | 是否必需插件（不可被用户关闭） |
| `default_enabled` | boolean | 否 | 默认是否启用（新项目首次加载时），默认 false |
| `supersedes` | string[] | 否 | 替代的旧插件名列表，启用此插件时自动禁用被替代插件 |
| `description` | string | 是 | 简短描述（默认语言） |
| `dependencies` | string[] | 否 | 依赖插件 ID 列表，用于拓扑排序 |
| `prompt` | object | 否 | Prompt 注入配置，详见 §3.3 |
| `capabilities` | object | 否 | 可调用能力声明，详见 §3.4 |
| `blocks` | object | 否 | Block 类型声明，详见 §3.5 |
| `events` | object | 否 | 事件声明，详见 §3.6 |
| `storage` | object | 否 | 存储 key 声明，详见 §3.7 |
| `permissions` | object | 否 | 权限声明，详见 §3.8 |
| `extensions` | object | 否 | 扩展命名空间（如 runtime_settings），详见 §3.9 |
| `max_triggers` | integer | 否 | 每个 session 中该插件最多触发次数。达到上限后自动排除。null/缺失 = 无限制 |
| `i18n` | object | 否 | 多语言翻译，详见 §3.10 |

### 3.3 `prompt` 字段

```json
{
  "position": "pre-response",
  "priority": 70,
  "template": "prompts/combat-instruction.md"
}
```

| 子字段 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `position` | enum | 是 | 注入位置：`system` / `character` / `world-state` / `memory` / `chat-history` / `pre-response` |
| `priority` | integer | 是 | 排序优先级，越小越先注入 |
| `template` | string | 否 | Jinja2 模板文件路径（相对插件目录）。缺失时使用 PLUGIN.md body |

**PromptBuilder 6 位置语义**：

| 位置 | 合并方式 | 用途 |
|------|---------|------|
| `system` | 合并为第一条 system message | world doc + global plugins |
| `character` | 合并为第一条 system message | character definitions |
| `world-state` | 合并为第一条 system message | plugin state data |
| `memory` | 合并为第一条 system message | long/short-term memory |
| `chat-history` | 解析为 role-specific messages | recent messages |
| `pre-response` | 追加为最终 system message | narrative-only 指令 |

> **V3 变化**：`pre-response` 不再包含 block 格式说明或 capability 列表。主 LLM 只关注叙事。
> Block 格式和 capability 信息由 Plugin Agent 通过预加载的 PLUGIN.md 获取。

**模板变量**（稳定上下文键）：

`project` / `characters` / `player` / `npcs` / `current_scene` / `scene_npcs` / `active_events` / `world_state` / `memories` / `archive` / `runtime_settings` / `runtime_settings_flat` / `story_images` / `compression_summary`

### 3.4 `capabilities` 字段

声明插件提供的可执行能力。Plugin Agent 通过 `execute_script()` 工具调用。

```json
{
  "dice.roll": {
    "description": "解析骰子表达式（如 2d6+3）并执行随机掷骰",
    "implementation": {
      "type": "script",
      "script": "scripts/roll.py",
      "timeout_ms": 5000
    },
    "result_block_type": "dice_result"
  }
}
```

| 子字段 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `description` | string | 是 | 能力描述（预加载到 Plugin Agent 系统提示中） |
| `implementation` | object | 是 | 执行配置 |
| `implementation.type` | enum | 是 | `"builtin"` / `"script"` / `"template"` |
| `implementation.script` | string | 当 type=script | 脚本相对路径（必须以 `scripts/` 开头） |
| `implementation.handler_name` | string | 当 type=builtin | 已注册的 builtin handler 名 |
| `implementation.template` | string | 当 type=template | Jinja2 模板相对路径 |
| `implementation.timeout_ms` | integer | 否 | 超时（仅 script），默认 5000，范围 100-60000 |
| `input_schema` | string | 否 | 输入 JSON Schema 文件路径 |
| `output_schema` | string | 否 | 输出 JSON Schema 文件路径 |
| `result_block_type` | string | 否 | 执行结果封装为哪个 block type 发送到前端 |

### 3.5 `blocks` 字段

声明插件可以 emit 的 block 类型。Plugin Agent 通过 `emit_block()` 工具输出。

```json
{
  "dice_result": {
    "schema": {
      "type": "object",
      "properties": {
        "dice": { "type": "string" },
        "result": { "type": "integer" }
      },
      "required": ["dice", "result"]
    },
    "handler": {
      "actions": [
        { "type": "storage_write", "key": "last-roll" },
        { "type": "emit_event", "event": "dice-rolled" }
      ]
    },
    "ui": { "component": "card", "title": "🎲 {{ dice }}" },
    "requires_response": false
  }
}
```

| 子字段 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `schema` | string or object | 否 | 外部 schema 文件路径（string）或内联 schema（object） |
| `handler` | object | 否 | 声明式 handler 配置 |
| `handler.actions` | array | 否 | 动作列表，支持的 action type 见下 |
| `ui` | object | 否 | 前端 schema 渲染配置 |
| `requires_response` | boolean | 否 | 默认 false。为 true 时前端将 block 视为交互 block |

> **V3 变化**：移除了 `instruction` 字段。在 V2 中，`instruction` 用于告诉主 LLM 如何输出 block 格式。
> V3 中主 LLM 不再输出 blocks，Plugin Agent 通过预加载的 PLUGIN.md 指令自行决定如何 `emit_block()` 或 `update_and_emit()`。

**支持的 handler action types**：

| Action Type | 语义 |
|------------|------|
| `builtin` | 委托已注册的内置处理器（需 `handler_name` 字段） |
| `storage_write` | 写插件存储（需 `key` 字段） |
| `emit_event` | 发射事件到请求级 event bus（需 `event` 字段） |
| `update_character` | 更新角色 |
| `create_event` | 创建游戏事件 |

未知 action type：记录 warning 并跳过。

**支持的 UI component types**：

`card` / `buttons` / `banner` / `custom` / `none`

`custom` 通过 `renderer_name` 绑定前端 `registerBlockRenderer()` 注册的组件。

### 3.6 `events` 字段

```json
{
  "emit": ["dice-rolled"],
  "listen": []
}
```

`listen` 中的 actions 通过 `DeclarativeBlockHandler` 执行。

### 3.7 `storage` 字段

```json
{
  "keys": ["last-roll", "config"]
}
```

声明插件使用的存储 key。物理表 `PluginStorage`，逻辑键 `(project_id, plugin_name, key) → value_json`。

### 3.8 `permissions` 字段

```json
{
  "network": false,
  "filesystem_scope": ["plugin", "data"],
  "script_languages": ["python"]
}
```

| 子字段 | 默认值（global） | 默认值（gameplay） | 说明 |
|--------|----------------|------------------|------|
| `network` | `true` | `false` | 是否允许联网 |
| `filesystem_scope` | `["plugin", "data"]` | `["plugin", "data"]` | 文件系统访问范围 |
| `script_languages` | `["python"]` | `["python"]` | 允许的脚本语言（Phase 1 仅 python） |

若 manifest 未声明 `permissions`，按插件 `type` 应用默认值。

### 3.9 `extensions` 字段

用于扩展命名空间，如 runtime_settings：

```json
{
  "runtime_settings": {
    "settings": [
      {
        "key": "category_count",
        "type": "integer",
        "default": 3,
        "min": 2,
        "max": 4,
        "i18n": {
          "zh": { "label": "分类数量", "description": "每次生成的建议分类数" }
        }
      }
    ]
  }
}
```

运行时对未知 extension 命名空间采取"忽略但保留"策略。

### 3.10 `i18n` 字段

```json
{
  "en": { "name": "Combat", "description": "Turn-based combat system." },
  "zh": { "name": "战斗系统", "description": "回合制战斗、骰子判定与状态效果。" }
}
```

| 子字段 | 类型 | 说明 |
|--------|------|------|
| `{locale}.name` | string | 插件显示名称 |
| `{locale}.description` | string | 插件描述 |

前端根据用户语言偏好选择对应翻译。所有自带插件**必须**同时提供 `en` 和 `zh`。

`extensions.runtime_settings` 中的每个 setting 也支持 `i18n` 子字段（覆盖 `label` 和 `description`）。

---

## 4. `PLUGIN.md` 规范

PLUGIN.md 是 Plugin Agent 的"运行手册"。在并行模式下，PLUGIN.md 内容作为系统提示词预加载到插件的独立 LLM 调用中。

### 4.1 frontmatter 字段

```yaml
---
name: combat
description: 回合制战斗、骰子判定、技能检定与状态效果。
when_to_use:
  - 叙事中发生战斗或冲突
  - 需要技能检定或骰子判定
  - 角色受到状态效果影响
avoid_when:
  - 纯对话或探索无战斗
  - 已有确定结果的行动
---
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 必须与 manifest.json.name 一致 |
| `description` | string | 是 | Plugin Agent 可读的插件描述 |
| `when_to_use` | string[] | 否 | Plugin Agent 判断何时使用此插件的正向条件 |
| `avoid_when` | string[] | 否 | Plugin Agent 判断何时不使用此插件的负向条件 |

> **V3 变化**：移除 `version` 和 `capability_summary` 字段。版本信息由 manifest.json 管理；
> capability 信息通过预加载的 manifest 数据获取。

### 4.2 一致性规则

`PLUGIN.md.name` 必须等于 `manifest.json.name`，否则导入期校验失败。

### 4.3 body 推荐章节

PLUGIN.md 正文是 Plugin Agent 加载后看到的核心指令。推荐章节结构：

```markdown
# Purpose
简要说明插件职责。

# 工作流程
1. 分析叙事，判断是否需要更新游戏状态
2. 有变化时用 update_and_emit 一次完成 DB 写入 + 前端通知
3. 纯展示插件直接用 emit_block

# DB 存储规范
- 角色数据：update_and_emit(writes=[{collection:"characters", key:"<角色名>", value:{...}}])
- 世界状态：update_and_emit(writes=[{collection:"world", key:"<key>", value:{...}}])
- （按插件职责列出具体的 collection/key 约定）

# Blocks
## state_update
描述何时 emit 此 block，以及 data 格式要求。
**通过 update_and_emit 的 emits 参数输出。**

## character_sheet
描述何时 emit 此 block，以及 data 格式要求。

# Capabilities
- dice.roll: 何时使用、参数说明

# Fallback
脚本失败或异常情况的降级策略。

# Rules
- 规则 1
- 规则 2
```

**关键原则**：
- body 中的指令面向 Plugin Agent，不面向主 LLM
- **DB 优先**：使用 `update_and_emit` 一次完成 DB 写入 + 前端通知（guide 等纯展示插件用 `emit_block`）
- 告诉 Plugin Agent 何时 `update_and_emit()`、何时 `emit_block()`、何时 `execute_script()`
- 不需要写 `json:xxx` 代码块格式说明（Plugin Agent 直接用工具）
- 游戏状态已在上下文中，无需 `db_read` 查询已有数据

### 4.4 Prompt 注入（双重用途）

PLUGIN.md body 还有第二个用途：通过 `manifest.json.prompt` 配置注入到**主 LLM** 的叙事 prompt 中。
这允许插件向主 LLM 提供上下文信息（如角色状态、记忆摘要），而非操作指令。

若 manifest.json.prompt.template 指向外部 Jinja2 文件，则 prompt 注入使用模板而非 body。

---

## 5. Plugin Agent 工具

Plugin Agent 通过 function calling 使用以下 7 个工具（从 V2 的 14 个优化而来）。插件开发者无需编写这些工具的代码——它们是平台内置的。

### 5.1 复合操作（最常用）

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `update_and_emit(writes, emits?, logs?)` | `writes: [{collection, key, value}]`, `emits?: [{type, data}]`, `logs?: [{collection, entry}]` | `{status, writes_count, emits_count, logs_count}` | 批量 DB 写入 + 可选输出多个 block + 可选追加多条日志。一次调用完成所有操作 |

> **这是最常用的工具**。大多数插件只需一次 `update_and_emit` 调用即可完成所有操作（DB 写入 + 前端通知 + 日志追加）。

### 5.2 纯展示 Block 输出

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `emit_block(type, data)` | `type: string, data: object` | `{status: "emitted"}` | 输出纯展示 block（无需 DB 写入的插件用，如 guide） |

### 5.3 数据读取

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `db_read(collection, key?)` | `collection: string, key?: string` | 单条数据或 collection 全部 | 统一读取（指定 key 读单条，不传 key 返回全部）。注意：游戏状态已在上下文中，仅在需要最新数据时使用 |

### 5.4 日志操作

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `db_log_append(collection, entry)` | `collection: string, entry: object` | `{status: "appended"}` | 追加日志条目（也可通过 `update_and_emit` 的 `logs` 参数批量追加） |
| `db_log_query(collection, limit?)` | `collection: string, limit?: int` | 日志条目列表 | 查询日志（默认 limit=10） |

### 5.5 关系图

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `db_graph_add(from_id, to_id, relation, data?)` | `from_id, to_id, relation: string, data?: object` | `{status: "added"}` | 添加关系边（NPC 关系、阵营关系等） |

### 5.6 脚本执行

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `execute_script(plugin, function, args?)` | `plugin: string, function: string, args?: object` | 脚本输出 JSON | 执行 manifest.capabilities 中声明的脚本 |

### 5.7 已移除的工具

以下工具在 V3 优化中已移除（后端保留向后兼容处理）：

| 旧工具 | 替代方案 |
|--------|---------|
| `list_plugins()` | 已移除（PLUGIN.md 预加载为系统提示） |
| `load_plugin(name)` | 已移除（PLUGIN.md 预加载为系统提示） |
| `db_kv_get(collection, key)` | 使用 `db_read(collection, key)` |
| `db_kv_set(collection, key, value)` | 使用 `update_and_emit(writes=[...])` |
| `db_kv_query(collection)` | 使用 `db_read(collection)` |
| `db_graph_query(...)` | 已移除 |

**Collection 命名规范**（所有插件必须遵循）：

| Collection | 用途 | 示例 key |
|-----------|------|---------|
| `characters` | 角色数据（attributes, inventory, status） | `"李逍遥"` |
| `world` | 世界状态（location, time, weather） | `"current_location"` |
| `npc` | NPC 数据（name, role, affinity） | `"王大锤"` |
| `event` | 事件记录 | `"event_discover_sword"` |
| `quest` | 任务数据 | `"explore_cave"` |
| `codex` | 知识条目 | `"location_qingyun_cave"` |
| `combat_log` | 战斗日志（用 db_log_append） | — |
| `plugin.<name>` | 插件私有数据 | `"memory_1"` |

**DB 优先原则**：使用 `update_and_emit` 一次完成 DB 写入和前端通知。DB 是游戏状态的唯一真实来源。纯展示插件（如 guide）直接用 `emit_block`。

**延迟提交**：每个插件使用 `GameDB(autocommit=False)`，所有 DB 写入在插件执行完毕后统一 `flush()` 提交，减少 I/O 开销。

### 5.8 工作流程示例

```
Plugin Agent 收到叙事文本 + 游戏状态 + 启用插件列表
  │
  ├─ 过滤：排除已达 max_triggers 上限的插件
  │
  ├─ 并行启动（asyncio.gather）：
  │     │
  │     ├─ combat 插件的 LLM 调用（PLUGIN.md 已预加载为系统提示）
  │     │     GameDB(autocommit=False) — 延迟提交
  │     │     ├─ 调用 execute_script("combat", "dice.roll", {"expr": "1d20+5"})
  │     │     ├─ 调用 update_and_emit(
  │     │     │     writes=[
  │     │     │       {collection:"characters", key:"李逍遥", value:{...}},
  │     │     │     ],
  │     │     │     emits=[
  │     │     │       {type:"dice_result", data:{dice:"1d20+5", result:18, ...}},
  │     │     │       {type:"combat_end", data:{outcome:"victory", ...}},
  │     │     │     ],
  │     │     │     logs=[
  │     │     │       {collection:"combat_log", entry:{...}},
  │     │     │     ]
  │     │     │   )
  │     │     └─ flush() ← 统一提交
  │     │
  │     ├─ state 插件的 LLM 调用（同时进行）
  │     │     ├─ 调用 update_and_emit(
  │     │     │     writes=[{collection:"characters", key:"李逍遥", value:{...}}],
  │     │     │     emits=[{type:"state_update", data:{characters:[{...}]}}]
  │     │     │   )
  │     │     └─ flush()
  │     │
  │     └─ guide 插件的 LLM 调用（同时进行，纯展示无需 DB）
  │           └─ 调用 emit_block("guide", {"categories": [...]})
  │
  ├─ 合并所有插件的 blocks
  │
  └─ 更新 plugin_trigger_counts
```

---

## 6. 脚本执行契约

### 6.1 执行方式

```
Plugin Agent 调用 execute_script(plugin, function, args)
  └─ 后端查 manifest.capabilities[function].implementation
       └─ type == "script" → ScriptRunner.run(script_path, args)
            └─ subprocess: python scripts/roll.py
                 stdin  ← JSON(args)
                 stdout → JSON(result)
                 exit_code → 0=成功, 非0=失败
```

### 6.2 stdin/stdout JSON 契约

**stdin**（由 ScriptRunner 写入）：

```json
{
  "expr": "2d6+3"
}
```

**stdout**（脚本输出）：

```json
{
  "dice": "2d6+3",
  "result": 11,
  "detail": [4, 4],
  "mod": 3,
  "success": true,
  "description": "掷出 2d6+3 = 4+4+3 = 11"
}
```

stdout 必须是合法 JSON。非 JSON 输出视为脚本错误。

### 6.3 退出码

| 退出码 | 语义 |
|--------|------|
| 0 | 成功，stdout 为结果 JSON |
| 非 0 | 失败，stderr 为错误信息 |

### 6.4 审计记录

每次脚本执行记录到 AuditLogger：

```json
{
  "invocation_id": "inv_abc123",
  "plugin": "combat",
  "capability": "dice.roll",
  "script": "scripts/roll.py",
  "args": { "expr": "2d6+3" },
  "exit_code": 0,
  "duration_ms": 62,
  "timestamp": "2026-02-24T10:00:00Z"
}
```

---

## 7. Schema 文件规范

### 7.1 索引优先

若存在 `schemas/index.yaml` 或 `schemas/index.json`，按索引加载：

```yaml
blocks:
  dice_result: schemas/blocks/dice_result.yaml
ui:
  dice_result: schemas/ui/dice_result_card.yaml
capabilities:
  dice_roll_input: schemas/capabilities/dice_roll_input.json
```

### 7.2 扫描回退

无索引时，按固定目录扫描：`schemas/blocks/` / `schemas/ui/` / `schemas/capabilities/`

### 7.3 文件格式

- 支持扩展名：`.json` / `.yaml` / `.yml`
- 解析后统一转为内部 JSON Schema 表示

---

## 8. 校验规则

### 8.1 加载期校验（PluginEngine.load）

| 规则 | 说明 |
|------|------|
| manifest.json 存在 | 必需 |
| manifest.json 可解析 | JSON 格式合法 |
| schema_version == "2.0" | 版本匹配 |
| name 与目录名一致 | `manifest.json.name` == 目录名 |
| name 格式合法 | 小写字母/数字/连字符，不以连字符开头或结尾 |
| PLUGIN.md 存在 | 必需 |
| PLUGIN.md frontmatter 可解析 | YAML 格式合法 |
| name 跨文件一致性 | PLUGIN.md.name == manifest.name |

### 8.2 导入期校验（import/validate）

| 规则 | 说明 |
|------|------|
| 必填字段齐全 | manifest.json 的 schema_version / name / version / type / required / description |
| dependencies 引用可解析 | 被依赖插件存在 |
| prompt.template 路径存在 | 如声明 |
| capabilities 中 script 路径存在 | 如 implementation.type == "script" |
| schemas 可解析 | 索引或扫描均可成功加载 |
| i18n 双语齐全 | 自带插件必须同时有 en 和 zh |
| External 必需文件 | README.md + schemas/ 目录存在 |

### 8.3 运行期校验（Plugin Agent 工具执行时）

| 规则 | 说明 |
|------|------|
| 插件已启用 | `execute_script` 引用的插件在 enabled_names 中 |
| capability 已声明 | 引用的 capability 在 manifest.capabilities 中 |
| block_data 符合 schema | `emit_block` 的数据通过 validate_block_data |
| 脚本路径在允许范围内 | 仅 scripts/ 子目录 |

---

## 9. 完整插件示例（V3）

### 9.1 combat 插件（rpg-mechanics 分组）

**目录结构**：

```text
plugins/rpg-mechanics/combat/
├── PLUGIN.md
├── manifest.json
├── prompts/
│   └── combat-instruction.md
└── scripts/
    └── roll.py
```

**PLUGIN.md**：

```markdown
---
name: combat
description: 统一战斗系统：回合制战斗、骰子判定、技能检定与状态效果。
when_to_use:
  - 玩家与敌人发生战斗
  - 需要随机判定（攻击/防御/技能检定）
  - 玩家尝试需要判定的技能行动
  - 角色被施加增益或减益效果
avoid_when:
  - 纯叙事无战斗或检定
  - 结果已经确定的行动
---

# Purpose
处理战斗机制：回合制战斗、骰子判定、技能检定、状态效果管理。

# 工作流程
1. 分析叙事，判断是否涉及战斗或检定
2. 需要随机判定时用 execute_script("combat", "dice.roll", {...})
3. 用 update_and_emit 一次完成：角色属性更新 + 战斗日志 + 前端通知

# DB 存储规范
- 角色属性更新：update_and_emit(writes=[{collection:"characters", key:"<角色名>", value:{name, attributes, inventory}}])
- 战斗日志：通过 update_and_emit 的 logs 参数追加：logs=[{collection:"combat_log", entry:{participants, outcome, ...}}]

# Blocks

## dice_result
当需要随机判定时输出。**通过 update_and_emit 的 emits 参数输出。**
- emits=[{type:"dice_result", data:{"dice": "2d6+3", "result": 11, "success": true, "description": "..."}}]
- 必需字段：dice, result
- 可选字段：success, description

## combat_start
战斗开始时 emit：
- emits=[{type:"combat_start", data:{"enemies": [...], "initiative_order": [...]}}]

## combat_end
战斗结束时 emit。**通过 update_and_emit 同时更新角色属性和输出 block。**
- update_and_emit(writes=[...], emits=[{type:"combat_end", data:{"outcome": "victory", "rewards": [...]}}])

# Capabilities
- dice.roll: 调用 execute_script("combat", "dice.roll", {"expr": "2d6+3"})
  返回 {"dice": "2d6+3", "result": 11, "detail": [4,4], "mod": 3}

# Rules
- 每个判定使用 execute_script 确保公正随机
- 战斗状态变化通过 update_and_emit 一次完成
- 不要在纯叙事中无故发起判定
```

### 9.2 guide 插件（narrative 分组，纯展示）

**目录结构**（无脚本的纯展示插件，无需 DB 持久化）：

```text
plugins/narrative/guide/
├── PLUGIN.md
├── manifest.json
└── prompts/
    └── guide-instruction.md
```

**PLUGIN.md**：

```markdown
---
name: guide
description: 为玩家提供行动建议和互动选项。
when_to_use:
  - 叙事结束后玩家需要行动方向
  - 场景切换或重要剧情节点
avoid_when:
  - 玩家已经明确表达了行动意图
  - 战斗正在进行中
---

# Purpose
分析叙事内容，生成分类行动建议供玩家选择。
本插件是纯展示插件，不需要 DB 持久化，直接 emit_block 即可。

# Blocks

## guide
每次叙事结束后 emit：
- emit_block("guide", {
    "categories": [
      {"style": "safe", "label": "稳妥", "suggestions": ["..."]},
      {"style": "bold", "label": "大胆", "suggestions": ["..."]},
      {"style": "creative", "label": "创意", "suggestions": ["..."]}
    ]
  })
- categories 数量由 runtime_settings 的 category_count 决定（默认 3）

# Rules
- 建议应与当前叙事紧密相关
- 每个 category 至少 1 条建议
- 风格标签必须包含 safe 和 bold
- 本插件无需 update_and_emit，直接 emit_block
```

---

## 10. 验收测试场景

### 加载与校验

1. **manifest 加载**：有 manifest.json 的插件正确解析 manifest + PLUGIN.md
2. **name 一致性校验**：PLUGIN.md 与 manifest 的 name 不一致时导入失败
3. **必填字段缺失**：manifest.json 缺少 schema_version 时校验报错
4. **name 格式校验**：name 含大写字母或空格时校验报错
5. **分组目录发现**：`plugins/<group>/<plugin>/` 结构正确发现

### Plugin Agent 工具

6. **update_and_emit**：批量 DB 写入 + 多个 block 输出 + 多条日志追加在一次调用中完成
7. **emit_block**：纯展示 block 正确输出
8. **db_read**：单 key 读取和 collection 全量读取均正确
9. **execute_script**：脚本正确执行并返回 JSON 结果
10. **db_log_*/db_graph_add**：日志和关系图操作正确
11. **延迟提交**：GameDB(autocommit=False) + flush() 正确批量提交

### Prompt 注入

11. **6 位置注入**：各插件按 manifest.prompt 的 position/priority 注入正确位置
12. **模板渲染**：Jinja2 模板正确渲染上下文变量
13. **纯叙事 prompt**：pre-response 不包含 block 格式说明

### 安全与审计

14. **网络策略**：gameplay 插件脚本联网默认拒绝
15. **文件系统范围**：脚本仅可访问插件目录和 data/
16. **审计完整性**：每次脚本执行有 invocation_id / exit_code / duration_ms 记录

### i18n

17. **双语必备**：所有自带插件有 en + zh 翻译
18. **前端显示**：PluginPanel 根据语言偏好显示正确的插件名和描述

---

## 11. 假设与默认值

1. 首期脚本语言仅支持 Python。
2. 首期不做插件导出。
3. 首期不做项目级模板覆盖。
4. 所有自带插件必须提供 `i18n.en` + `i18n.zh`。
5. Plugin Agent 每个插件最多执行 8 轮工具调用（`MAX_TOOL_ROUNDS = 8`），所有插件并行执行，每个插件使用延迟提交（`GameDB(autocommit=False)`）。
6. 主 LLM 不输出任何 block，所有 block 由 Plugin Agent 的 `update_and_emit()` 或 `emit_block()` 产出。

---

文档版本：v3.1（工具优化：14→7，复合操作 update_and_emit，延迟提交）
更新日期：2026-02-24
