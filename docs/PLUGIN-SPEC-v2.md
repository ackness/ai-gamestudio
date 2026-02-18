# AI GameStudio Plugin Spec v2.0

> 本文是 V2 实现规范（runtime contract）。实现者按本文可直接编码，无决策空白。
>
> 与 V1 的关系：V2 兼容 V1 插件（自动回退）；新插件应使用 V2 格式。
>
> 架构蓝图：`docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md`（设计原则、迁移映射、执行流程）。

---

## 1. 插件包结构

### 1.1 Builtin 插件（最小 2 文件）

```text
my-plugin/
├── PLUGIN.md           # LLM 运行手册（必需）
├── manifest.json       # 机器事实源（必需）
├── prompts/            # Jinja2 模板（可选）
│   └── *.md
├── scripts/            # 可执行脚本（可选）
│   └── *.py
└── references/         # 参考文档（可选）
```

### 1.2 External 插件（完整 4 文件）

```text
my-plugin/
├── PLUGIN.md           # LLM 运行手册（必需）
├── manifest.json       # 机器事实源（必需）
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

### 1.3 职责分离

| 文件 | 受众 | 职责 |
|------|------|------|
| `PLUGIN.md` | LLM | 运行手册：触发条件、执行步骤、输出要求、降级策略 |
| `manifest.json` | 运行时 | 唯一事实源：依赖、权限、能力、入口、blocks、events、storage |
| `README.md` | 开发者 | 安装、调试、测试说明 |
| `schemas/` | 运行时 + 前端 | block/ui schema 契约 |

---

## 2. `manifest.json` 完整字段定义

### 2.1 示例

```json
{
  "schema_version": "2.0",
  "name": "dice-roll",
  "version": "2.0.0",
  "type": "gameplay",
  "required": false,
  "description": "Optional dice-result block plugin with storage write and event emission.",
  "dependencies": [],

  "prompt": {
    "position": "pre-response",
    "priority": 70,
    "template": "prompts/dice-instruction.md"
  },

  "capabilities": {
    "dice.roll": {
      "description": "Parse dice expression and roll",
      "implementation": {
        "type": "script",
        "script": "scripts/roll.py",
        "timeout_ms": 5000
      },
      "input_schema": "schemas/capabilities/dice_roll_input.json",
      "output_schema": "schemas/capabilities/dice_roll_output.json",
      "result_block_type": "dice_result"
    }
  },

  "blocks": {
    "dice_result": {
      "instruction": "当需要随机判定时（攻击/防御/技能检定/概率事件），你必须输出此 block...",
      "schema": "schemas/blocks/dice_result.yaml",
      "handler": {
        "actions": [
          { "type": "storage_write", "key": "last-roll" },
          { "type": "emit_event", "event": "dice-rolled" }
        ]
      },
      "ui": {
        "component": "card",
        "title": "🎲 {{ dice }}",
        "sections": [
          { "type": "key-value", "fields": ["result", "success", "description"] }
        ]
      },
      "requires_response": false
    }
  },

  "events": {
    "emit": ["dice-rolled"],
    "listen": []
  },

  "storage": {
    "keys": ["last-roll"]
  },

  "permissions": {
    "network": false,
    "filesystem_scope": ["plugin", "data"],
    "script_languages": ["python"]
  },

  "extensions": {}
}
```

### 2.2 字段定义

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `schema_version` | string | 是 | 固定为 `"2.0"` |
| `name` | string | 是 | 插件唯一 ID，必须与目录名一致，格式：小写字母/数字/连字符 |
| `version` | string | 是 | 插件版本（建议 semver） |
| `type` | enum | 是 | `"global"` 或 `"gameplay"` |
| `required` | boolean | 是 | 是否必需插件（不可被用户关闭） |
| `description` | string | 是 | 简短描述 |
| `dependencies` | string[] | 否 | 依赖插件 ID 列表，用于拓扑排序 |
| `prompt` | object | 否 | Prompt 注入配置，详见 §2.3 |
| `capabilities` | object | 否 | 可调用能力声明，详见 §2.4 |
| `blocks` | object | 否 | Block 类型声明，详见 §2.5 |
| `events` | object | 否 | 事件声明，详见 §2.6 |
| `storage` | object | 否 | 存储 key 声明，详见 §2.7 |
| `permissions` | object | 否 | 权限声明，详见 §2.8 |
| `extensions` | object | 否 | 扩展命名空间（如 runtime_settings），详见 §2.9 |

### 2.3 `prompt` 字段

```json
{
  "position": "pre-response",
  "priority": 70,
  "template": "prompts/dice-instruction.md"
}
```

| 子字段 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `position` | enum | 是 | 注入位置：`system` / `character` / `world-state` / `memory` / `chat-history` / `pre-response` |
| `priority` | integer | 是 | 排序优先级，越小越先注入 |
| `template` | string | 否 | Jinja2 模板文件路径（相对插件目录）。缺失时使用 PLUGIN.md body |

**PromptBuilder 6 位置语义**（与 V1 完全一致）：

| 位置 | 合并方式 | 用途 |
|------|---------|------|
| `system` | 合并为第一条 system message | world doc + global plugins |
| `character` | 合并为第一条 system message | character definitions |
| `world-state` | 合并为第一条 system message | plugin state data |
| `memory` | 合并为第一条 system message | long/short-term memory |
| `chat-history` | 解析为 role-specific messages | recent messages |
| `pre-response` | 追加为最终 system message | block instructions + capability list |

**模板变量**（稳定上下文键，与 V1 一致）：

`project` / `characters` / `player` / `npcs` / `current_scene` / `scene_npcs` / `active_events` / `world_state` / `memories` / `archive` / `runtime_settings` / `runtime_settings_flat` / `story_images`

### 2.4 `capabilities` 字段

```json
{
  "dice.roll": {
    "description": "Parse dice expression and roll",
    "implementation": {
      "type": "script",
      "script": "scripts/roll.py",
      "timeout_ms": 5000
    },
    "input_schema": "schemas/capabilities/dice_roll_input.json",
    "output_schema": "schemas/capabilities/dice_roll_output.json",
    "result_block_type": "dice_result"
  }
}
```

| 子字段 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `description` | string | 是 | 能力描述（注入 pre-response 供 LLM 判断） |
| `implementation` | object | 是 | 执行配置 |
| `implementation.type` | enum | 是 | `"builtin"` / `"script"` / `"template"` |
| `implementation.script` | string | 当 type=script | 脚本相对路径（必须以 `scripts/` 开头） |
| `implementation.handler_name` | string | 当 type=builtin | 已注册的 builtin handler 名 |
| `implementation.template` | string | 当 type=template | Jinja2 模板相对路径 |
| `implementation.timeout_ms` | integer | 否 | 超时（仅 script），默认 5000，范围 100-60000 |
| `input_schema` | string | 否 | 输入 JSON Schema 文件路径 |
| `output_schema` | string | 否 | 输出 JSON Schema 文件路径 |
| `result_block_type` | string | 否 | 执行结果封装为哪个 block type 发送到前端 |

### 2.5 `blocks` 字段

与 V1 frontmatter 的 `blocks` 结构一致，移入 manifest：

```json
{
  "dice_result": {
    "instruction": "当需要随机判定时...",
    "schema": "schemas/blocks/dice_result.yaml",
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
}
```

| 子字段 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `instruction` | string | 否 | 注入 pre-response 的 block 使用说明（含 fenced block 示例） |
| `schema` | string or object | 否 | 外部 schema 文件路径（string）或内联 schema（object） |
| `handler` | object | 否 | 声明式 handler 配置 |
| `handler.actions` | array | 否 | 动作列表，支持的 action type 见下 |
| `ui` | object | 否 | 前端 schema 渲染配置 |
| `requires_response` | boolean | 否 | 默认 false。为 true 时前端将 block 视为交互 block |

**支持的 handler action types**（V1 保持不变）：

| Action Type | 语义 |
|------------|------|
| `builtin` | 委托已注册的内置处理器（需 `handler_name` 字段） |
| `storage_write` | 写插件存储（需 `key` 字段） |
| `emit_event` | 发射事件到请求级 event bus（需 `event` 字段） |
| `update_character` | 更新角色 |
| `create_event` | 创建游戏事件 |

未知 action type：记录 warning 并跳过。

**支持的 UI component types**（V1 保持不变）：

`card` / `buttons` / `banner` / `custom` / `none`

`custom` 通过 `renderer_name` 绑定前端 `registerBlockRenderer()` 注册的组件。

### 2.6 `events` 字段

```json
{
  "emit": ["dice-rolled"],
  "listen": [
    {
      "dice-rolled": {
        "actions": [
          { "type": "storage_write", "key": "last-roll" }
        ]
      }
    }
  ]
}
```

与 V1 frontmatter 的 `events` 结构一致。`listen` 中的 actions 通过 `DeclarativeBlockHandler` 执行。

### 2.7 `storage` 字段

```json
{
  "keys": ["last-roll", "config"]
}
```

声明插件使用的存储 key。物理表 `PluginStorage`，逻辑键 `(project_id, plugin_name, key) → value_json`。

### 2.8 `permissions` 字段

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

### 2.9 `extensions` 字段

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
        "max": 4
      }
    ]
  }
}
```

运行时对未知 extension 命名空间采取"忽略但保留"策略。

---

## 3. `PLUGIN.md` frontmatter 规范

### 3.1 字段定义

V2 的 PLUGIN.md frontmatter **仅保留 LLM 相关字段**，其余全部移入 manifest.json：

```yaml
---
name: dice-roll
version: 2.0.0
description: 处理骰子检定与概率判定。
when_to_use:
  - 需要随机判定（攻击/防御/技能检定）
  - 需要命中/豁免计算
avoid_when:
  - 纯叙事无检定
  - 已经有确定结果的行动
capability_summary: |
  提供骰子解析、执行与结构化结果输出能力。
  可通过 json:plugin_use 调用 dice.roll capability。
---
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 必须与 manifest.json.name 一致 |
| `version` | string | 是 | 必须与 manifest.json.version 一致 |
| `description` | string | 是 | LLM 可读的插件描述 |
| `when_to_use` | string[] | 否 | LLM 判断何时使用此插件的正向条件 |
| `avoid_when` | string[] | 否 | LLM 判断何时不使用此插件的负向条件 |
| `capability_summary` | string | 否 | LLM 选择 capability 时的摘要提示 |

### 3.2 一致性规则

1. `PLUGIN.md.name` 必须等于 `manifest.json.name`
2. `PLUGIN.md.version` 必须等于 `manifest.json.version`
3. 任一不一致，**导入期校验失败**（不是运行时猜测）

### 3.3 when_to_use / avoid_when 的语义

这两个字段是 **LLM 提示词**，不是规则引擎输入：

- 运行时将 `when_to_use` / `avoid_when` 注入 pre-response 指令
- LLM 自行判断当前 turn 是否应使用此插件的能力
- 不存在 Rule Matcher 组件

---

## 4. `PLUGIN.md` body 推荐章节

正文建议固定以下章节结构，运行期作为 prompt 内容注入：

```markdown
# Purpose
对检定请求生成标准化随机结果。

# Capabilities
- dice.roll: 解析骰子表达式并执行随机掷骰

# Direct Blocks
## json:dice_result
当需要随机判定时输出此 block。格式：
...（含 fenced block 示例）

# Fallback
脚本失败时输出 json:notification，提示玩家手动判定。

# Rules
- 每个检定独立输出一个 dice_result block
- 不要在纯叙事中无故掷骰
```

**运行时要求**：
1. PLUGIN.md body 按 `manifest.json.prompt` 配置的 position/priority 注入 PromptBuilder
2. 若 manifest.json.prompt.template 指向外部 Jinja2 文件，body 仅在模板缺失时作为回退
3. body 中的 `# Direct Blocks` 章节应与 manifest.json.blocks 的 instruction 字段保持一致

---

## 5. `json:plugin_use` 协议

### 5.1 JSON Schema

```json
{
  "type": "object",
  "required": ["plugin", "capability", "args"],
  "properties": {
    "plugin": { "type": "string", "minLength": 1 },
    "capability": { "type": "string", "minLength": 1 },
    "args": { "type": "object" }
  },
  "additionalProperties": false
}
```

### 5.2 LLM 输出示例

````
```json:plugin_use
{
  "plugin": "dice-roll",
  "capability": "dice.roll",
  "args": { "expr": "2d6+3" }
}
```
````

### 5.3 后端处理流程

1. `block_parser.extract_blocks()` 提取 type == "plugin_use" 的 block
2. `dispatch_block()` 识别后交给 `CapabilityExecutor`
3. CapabilityExecutor：
   - 校验 `plugin` 是否已启用
   - 校验 `capability` 是否在 manifest.capabilities 中声明
   - 校验 `args` 符合 capability.input_schema（如声明）
   - 根据 `implementation.type` 分发执行
4. 执行结果封装为 `result_block_type` 指定的 block type
5. result block 走正常 dispatch_block 流程（可触发 handler actions / event bus）

### 5.4 与 Direct Blocks 的区别

| 维度 | Direct Output Blocks | Capability Invocation (plugin_use) |
|------|---------------------|-----------------------------------|
| LLM 职责 | 直接输出结构化数据 | 只声明调用意图 |
| 后端执行 | dispatch_block 既有路径 | CapabilityExecutor → implementation |
| 适用场景 | 简单状态更新、通知、选项 | 需要计算、外部调用、脚本执行 |
| 数据来源 | LLM 生成 | 后端执行生成 |

---

## 6. 脚本执行契约

### 6.1 执行方式

```
CapabilityExecutor
  └─ ScriptRunner.run(script_path, args)
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

即 `json:plugin_use` 的 `args` 字段原样传入。

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

每次脚本执行 ScriptRunner 必须记录到 AuditLogger：

```json
{
  "invocation_id": "inv_abc123",
  "plugin": "dice-roll",
  "capability": "dice.roll",
  "script": "scripts/roll.py",
  "args": { "expr": "2d6+3" },
  "exit_code": 0,
  "duration_ms": 62,
  "stdout": "{\"dice\":\"2d6+3\",\"result\":11,...}",
  "stderr": "",
  "timestamp": "2026-02-17T10:00:00Z"
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
  dice_roll_output: schemas/capabilities/dice_roll_output.json
```

### 7.2 扫描回退

无索引时，按固定目录扫描：

1. `schemas/blocks/`
2. `schemas/ui/`
3. `schemas/capabilities/`

### 7.3 文件格式

- 支持扩展名：`.json` / `.yaml` / `.yml`
- 解析后统一转为内部 JSON Schema 表示
- 同名冲突时：索引声明优先；索引缺失时按文件名冲突报错

---

## 8. 校验规则

### 8.1 加载期校验（PluginEngine.load）

| 规则 | 说明 |
|------|------|
| manifest.json 存在 | V2 插件必需；缺失则回退 V1 |
| manifest.json 可解析 | JSON 格式合法 |
| schema_version == "2.0" | 版本匹配 |
| name 与目录名一致 | `manifest.json.name` == 目录名 |
| name 格式合法 | 小写字母/数字/连字符，不以连字符开头或结尾 |
| PLUGIN.md 存在 | 必需 |
| PLUGIN.md frontmatter 可解析 | YAML 格式合法 |

### 8.2 导入期校验（import/validate）

| 规则 | 说明 |
|------|------|
| name/version 跨文件一致性 | PLUGIN.md.name == manifest.name，PLUGIN.md.version == manifest.version |
| 必填字段齐全 | manifest.json 的 schema_version / name / version / type / required / description |
| dependencies 引用可解析 | 被依赖插件存在于 builtin 或 library |
| prompt.template 路径存在 | 如声明 |
| capabilities 中 script 路径存在 | 如 implementation.type == "script" |
| schemas 可解析 | 索引或扫描均可成功加载 |
| permissions 策略合法 | network / filesystem_scope / script_languages 值在允许范围内 |
| External 必需文件 | README.md + schemas/ 目录存在 |

### 8.3 运行期校验（dispatch_block / CapabilityExecutor）

| 规则 | 说明 |
|------|------|
| 插件已启用 | plugin_use 引用的插件在 enabled_names 中 |
| 依赖已满足 | 依赖插件全部已启用 |
| capability 已声明 | plugin_use 的 capability 在 manifest.capabilities 中 |
| args 符合 input_schema | 如声明了 input_schema |
| block_data 符合 schema | block 数据通过 validate_block_data |
| 脚本路径在允许范围内 | 仅 scripts/ 子目录 |

---

## 9. V1 回退行为

当插件目录下**不存在 manifest.json** 时：

1. PluginEngine.load() 回退到 V1 路径：解析 PLUGIN.md frontmatter 获取全部元数据
2. 日志输出：`logger.warning("Plugin '{}' has no manifest.json, using V1 fallback", name)`
3. 后续流程统一：prompt injection / block declarations / event listeners 接口不变
4. V1 回退插件不能声明 capabilities（无 plugin_use 支持）
5. V1 回退是过渡机制，最终所有 builtin 插件应迁移到 V2

---

## 10. 完整插件示例

### 10.1 dice-roll V2

**目录结构**：

```text
plugins/dice-roll/
├── PLUGIN.md
├── manifest.json
├── prompts/
│   └── dice-instruction.md
└── scripts/
    └── roll.py
```

**manifest.json**：

```json
{
  "schema_version": "2.0",
  "name": "dice-roll",
  "version": "2.0.0",
  "type": "gameplay",
  "required": false,
  "description": "Optional dice-result block plugin with storage write and event emission.",
  "dependencies": [],

  "prompt": {
    "position": "pre-response",
    "priority": 70,
    "template": "prompts/dice-instruction.md"
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
      "instruction": "当需要随机判定时（攻击/防御/技能检定/概率事件），你必须输出 json:dice_result block。格式：\n```json:dice_result\n{\"dice\": \"2d6+3\", \"result\": 11, \"success\": true, \"description\": \"掷出 2d6+3 = 11\"}\n```\n不要在纯叙事中无故输出此 block。",
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
        "title": "🎲 {{ dice }}",
        "sections": [
          { "type": "key-value", "fields": ["result", "success", "description"] }
        ]
      },
      "requires_response": false
    }
  },

  "events": {
    "emit": ["dice-rolled"],
    "listen": []
  },

  "storage": {
    "keys": ["last-roll"]
  },

  "permissions": {
    "network": false,
    "filesystem_scope": ["plugin", "data"],
    "script_languages": ["python"]
  },

  "extensions": {}
}
```

**PLUGIN.md**：

```markdown
---
name: dice-roll
version: 2.0.0
description: 处理骰子检定与概率判定。
when_to_use:
  - 需要随机判定（攻击/防御/技能检定）
  - 需要命中/豁免计算
  - 概率事件需要公正裁决
avoid_when:
  - 纯叙事无检定
  - 已经有确定结果的行动
capability_summary: |
  提供骰子解析与执行能力。可直接输出 json:dice_result，
  或通过 json:plugin_use 调用 dice.roll capability 让后端掷骰。
---

# Purpose
对检定请求生成标准化随机结果。

# Capabilities
- dice.roll: 解析骰子表达式（如 2d6+3, 1d20）并输出结构化掷骰结果

# Direct Blocks

## json:dice_result
当需要随机判定时（攻击/防御/技能检定/概率事件），输出此 block：

` ` `json:dice_result
{"dice": "2d6+3", "result": 11, "success": true, "description": "掷出 2d6+3 = 4+4+3 = 11"}
` ` `

必需字段：dice, result。可选字段：success, description。

# Fallback
脚本失败时输出 json:notification，提示玩家手动判定。

# Rules
- 每个检定独立输出一个 dice_result block
- 不要在纯叙事中无故掷骰
- 重大判定建议使用 plugin_use 调用 dice.roll 以确保公正
```

### 10.2 core-blocks V2

**目录结构**：

```text
plugins/core-blocks/
├── PLUGIN.md
├── manifest.json
└── prompts/
    └── core-instruction.md
```

**manifest.json**：

```json
{
  "schema_version": "2.0",
  "name": "core-blocks",
  "version": "2.0.0",
  "type": "global",
  "required": true,
  "description": "Core block declarations for state sync, character sheets, scenes, events, and notifications.",
  "dependencies": [],

  "prompt": {
    "position": "system",
    "priority": 95,
    "template": "prompts/core-instruction.md"
  },

  "capabilities": {},

  "blocks": {
    "state_update": {
      "instruction": "当角色属性/背包/世界状态有变化时，必须输出 json:state_update block...",
      "handler": {
        "actions": [
          { "type": "builtin", "handler_name": "state_update" }
        ]
      },
      "ui": { "component": "none" },
      "requires_response": false
    },
    "character_sheet": {
      "instruction": "当需要创建或编辑角色卡时，输出 json:character_sheet block...",
      "handler": {
        "actions": [
          { "type": "builtin", "handler_name": "character_sheet" }
        ]
      },
      "ui": { "component": "custom", "renderer_name": "character_sheet" },
      "requires_response": false
    },
    "scene_update": {
      "instruction": "当玩家移动到新地点或场景描述变化时，输出 json:scene_update block...",
      "handler": {
        "actions": [
          { "type": "builtin", "handler_name": "scene_update" }
        ]
      },
      "ui": { "component": "custom", "renderer_name": "scene_update" },
      "requires_response": false
    },
    "event": {
      "instruction": "当故事事件发生变化时（创建/演变/解决/结束），输出 json:event block...",
      "handler": {
        "actions": [
          { "type": "builtin", "handler_name": "event" }
        ]
      },
      "ui": { "component": "none" },
      "requires_response": false
    },
    "notification": {
      "instruction": "当需要向玩家显示系统提示或警告时，输出 json:notification block...",
      "ui": { "component": "custom", "renderer_name": "notification" },
      "requires_response": false
    }
  },

  "events": {
    "emit": [],
    "listen": []
  },

  "storage": {
    "keys": []
  },

  "permissions": {},

  "extensions": {
    "runtime_settings": {
      "settings": [
        {
          "key": "narrative_tone",
          "type": "enum",
          "options": ["neutral", "grim", "heroic", "whimsical"],
          "default": "neutral",
          "affects": ["story"]
        },
        {
          "key": "pacing",
          "type": "enum",
          "options": ["slow", "balanced", "fast"],
          "default": "balanced",
          "affects": ["story", "choices"]
        },
        {
          "key": "response_length",
          "type": "enum",
          "options": ["short", "medium", "long"],
          "default": "medium",
          "affects": ["story"]
        },
        {
          "key": "risk_bias",
          "type": "enum",
          "options": ["safe", "balanced", "dangerous"],
          "default": "balanced",
          "affects": ["story", "choices"]
        }
      ]
    }
  }
}
```

**PLUGIN.md**：

```markdown
---
name: core-blocks
version: 2.0.0
description: 核心 block 类型定义：状态同步、角色卡、场景、事件、通知。
when_to_use:
  - 任何涉及角色/世界/场景/事件状态变化的回合
  - 需要向玩家显示重要提示时
avoid_when:
  - 纯对话无状态变化
capability_summary: |
  提供 state_update / character_sheet / scene_update / event / notification
  五种基础 block 类型，是其他插件的基础依赖。
---

# Purpose
定义基础 block 类型，由后端 dispatcher 和前端 renderer 消费。

# Direct Blocks

## json:state_update
角色属性/背包/世界状态变化时输出。

## json:character_sheet
创建或编辑角色卡时输出。

## json:scene_update
场景切换或描述更新时输出。

## json:event
故事事件创建/演变/解决/结束时输出。

## json:notification
向玩家显示系统提示时输出。

# Rules
- state_update 至少包含 characters 或 world 之一
- scene_update.action 必须是 move 或 update
- event.action 必须是 create / evolve / resolve / end 之一
```

---

## 11. 验收测试场景

### 加载与校验

1. **V2 加载**：有 manifest.json 的插件正确解析 manifest + PLUGIN.md
2. **V1 回退**：无 manifest.json 的插件回退到 V1 frontmatter 解析，日志输出警告
3. **一致性拒绝**：PLUGIN.md 与 manifest 的 name 不一致时导入失败
4. **版本一致性拒绝**：PLUGIN.md 与 manifest 的 version 不一致时导入失败
5. **必填字段缺失**：manifest.json 缺少 schema_version 时校验报错
6. **name 格式校验**：name 含大写字母或空格时校验报错

### Schema 加载

7. **索引加载**：有 schemas/index.yaml 时按索引路径加载 schema
8. **扫描回退**：无索引时扫描 schemas/blocks/ 等固定目录可成功加载
9. **schema 校验**：dice_result block data 不符合 schema 时被 validate_block_data 拒绝

### Prompt 注入

10. **6 位置注入**：各插件按 manifest.prompt 的 position/priority 注入正确位置
11. **pre-response 增强**：启用 capability 的插件在 pre-response 中包含 plugin_use 格式说明
12. **模板渲染**：Jinja2 模板正确渲染上下文变量（characters / world_state 等）

### plugin_use 协议

13. **正常调用**：LLM 输出 json:plugin_use → CapabilityExecutor 执行 → result block 返回
14. **未声明 capability 拒绝**：plugin_use 引用不存在的 capability 时返回错误
15. **未启用插件拒绝**：plugin_use 引用未启用的插件时返回错误
16. **脚本超时**：script 执行超过 timeout_ms 时中止并返回错误

### 安全与审计

17. **网络策略**：gameplay 插件脚本联网默认拒绝；global 插件默认允许
18. **文件系统范围**：脚本访问插件目录和 data/ 可通过，访问其他路径被拒绝
19. **审计完整性**：每次脚本执行在审计日志中有 invocation_id / exit_code / duration_ms / stdout / stderr

---

## 12. 假设与默认值

1. 首期脚本语言仅支持 Python。
2. 首期不做插件导出。
3. 首期不做项目级模板覆盖。
4. API 路径不加 `/v2`，直接增强现有语义。
5. 本规范中的"推荐"在首版实现中按"必须"执行。
6. 无 manifest.json 的插件自动回退 V1 解析路径。

---

文档版本：v2.0
更新日期：2026-02-17
