# AI GameStudio 插件规范 (Extensible) v1.0

> 说明：本文件是 **v1 兼容规范**（基于 `PLUGIN.md` frontmatter）。
>
> 新项目与重构请优先参考：`docs/PLUGIN-SPEC-v2.md`（Agent Skills 对齐、Skill-First 模型）。

> 目标：在不破坏现有运行时的前提下，定义一套可长期演进的插件规范。  
> 状态：本规范对齐当前代码实现，并为后续扩展预留稳定接口。

---

## 1. 设计目标

1. 声明优先：优先用 `PLUGIN.md` 声明能力，而不是硬编码。
2. 向后兼容：旧插件尽可能无需修改即可继续运行。
3. 可扩展：允许新增字段、动作、UI 类型、事件协议，而不重写整体框架。
4. 渐进增强：先支持最小可用能力，再逐步启用高级能力。
5. 运行时可降级：遇到未知扩展时，系统应安全忽略或降级处理。

---

## 2. 运行时能力分层

为避免“规范先行、实现滞后”的失配，插件能力分为两层：

### 2.1 Core（当前已实现，稳定）

- 插件发现、加载、校验
- 依赖排序（拓扑排序）
- Prompt 注入（Jinja2 模板）
- `blocks` 声明
- 声明式 block handler（部分动作）
- 请求级事件总线（`events.listen`）
- UI schema 驱动渲染（前端）
- 插件存储（`PluginStorage`）

### 2.2 Reserved（保留扩展位，当前不保证执行）

- `hooks`（on-turn/on-event/on-cron 等脚本执行）
- `llm`（插件级独立 LLM 任务调度）
- `exports.commands/queries`（插件 API 调用总线）

保留字段可以声明，但当前运行时不应假定其自动生效。

---

## 3. 插件目录结构

### 3.1 最小结构（推荐起点）

```text
my-plugin/
└── PLUGIN.md
```

### 3.2 推荐结构（便于扩展）

```text
my-plugin/
├── PLUGIN.md
├── prompts/
│   └── *.md
├── schemas/
│   └── *.yaml
├── scripts/          # 预留：未来 hooks 执行
└── references/       # 可选：详细文档
```

---

## 4. `PLUGIN.md` 结构约定

`PLUGIN.md` = YAML frontmatter + Markdown 正文。

### 4.1 必需字段（当前校验强制）

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 插件唯一 ID；需与目录名一致 |
| `description` | string | 简短描述 |
| `type` | enum | `global` 或 `gameplay` |
| `required` | bool | 是否必需插件 |

### 4.2 推荐字段（当前实现支持）

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | string | 插件自身版本（建议 semver） |
| `dependencies` | string[] | 依赖插件 ID；用于排序 |
| `prompt` | object | Prompt 注入配置 |
| `blocks` | object | Block 声明（指令、handler、ui） |
| `events` | object | 事件监听/发射声明 |
| `storage` | object | 存储 key 声明 |

### 4.3 保留字段（允许声明，当前不保证执行）

| 字段 | 说明 |
|---|---|
| `hooks` | 生命周期脚本声明 |
| `llm` | 插件级 LLM 配置 |
| `exports` | 插件命令/查询接口声明 |

### 4.4 扩展字段（关键）

为保证规范长期可扩展，新增字段应使用以下机制之一：

1. `extensions.<namespace>`（推荐）
2. 顶层 `x-<namespace>-<field>`（兼容常见 YAML 扩展习惯）

示例：

```yaml
extensions:
  acme:
    skill_tree:
      enabled: true
      max_depth: 5

x-acme-trace:
  emit_metrics: true
```

运行时对未知扩展字段应采取“忽略但保留”的策略。

---

## 5. Prompt 注入规范

### 5.1 `prompt` 配置

```yaml
prompt:
  position: pre-response
  priority: 80
  template: prompts/instruction.md
```

### 5.2 注入位置（当前实现）

- `system`
- `character`
- `world-state`
- `memory`
- `chat-history`
- `pre-response`

### 5.3 语义

- `priority` 越小，越先注入。
- `system/character/world-state/memory` 会合并为系统消息。
- `chat-history` 转为角色消息。
- `pre-response` 作为最终系统提示追加。

### 5.4 模板变量策略

模板应仅依赖“稳定上下文键”。当前推荐使用：

- `project`
- `characters`
- `player`
- `npcs`
- `current_scene`
- `scene_npcs`
- `active_events`
- `world_state`
- `memories`
- `archive`

建议：

- 模板里用 `{% if ... %}` 包裹可选字段，避免空注入。
- 以“上下文不存在时降级为空文本”为默认行为。

---

## 6. Block 规范（核心扩展点）

### 6.1 声明结构

````yaml
blocks:
  my_block:
    instruction: |
      何时输出 + 示例
      ```json:my_block
      {"k": "v"}
      ```
    schema: {...}
    handler:
      actions: [...]
    ui: {...}
    requires_response: false
````

### 6.2 `instruction`

- 会被注入到 pre-response 指令中。
- 必须包含 fenced block 示例（` ```json:<type> `）。
- 建议明确触发条件，避免每轮滥发 block。

### 6.3 `schema`

- 用于描述 JSON 结构（当前主要供前端/工具参考）。
- 不应假设后端已对所有 block 做严格 schema 校验。

### 6.4 `handler.actions`（当前支持）

| 动作 | 语义 |
|---|---|
| `builtin` | 委托内置处理器 |
| `storage_write` | 写插件存储 |
| `emit_event` | 发射事件到请求级 event bus |
| `update_character` | 更新角色 |
| `create_event` | 创建游戏事件 |

未知 action：记录 warning 并跳过，不中断整条消息处理。

### 6.5 `ui`（前端 schema 渲染）

`component` 当前支持：

- `card`
- `buttons`
- `banner`
- `custom`
- `none`

`custom` 通过 `renderer_name` 绑定前端注册组件。

### 6.6 `requires_response`

当为 `true`：

1. 前端将 block 视为交互 block。
2. 用户交互结果通过 `block_response` 回传。
3. 后端作为上下文注入下一轮 LLM 调用。

---

## 7. 事件规范

### 7.1 声明格式

```yaml
events:
  emit:
    - dice-rolled
  listen:
    - dice-rolled:
        actions:
          - type: storage_write
            key: last-roll
```

### 7.2 当前行为

- `events.listen`：当前运行时会注册并执行声明式 actions。
- `events.emit`：主要是声明用途；实际发射由 `emit_event` action 驱动。

### 7.3 命名建议（可扩展）

建议使用 `<plugin>.<event>` 或 `<domain>.<action>`，例如：

- `dice.roll.completed`
- `quest.mainline.advanced`

避免与通用词冲突（如 `update`, `done`）。

---

## 8. 存储规范

插件存储模型：

- 物理表：`PluginStorage`
- 逻辑键：`(project_id, plugin_name, key) -> value_json`

### 8.1 key 设计建议

1. 语义清晰：`short-term-memory`、`session-meta`
2. 可迁移：同一 key 内使用版本字段
3. 可分片：大对象拆为多个 key

示例：

```json
{
  "format_version": 2,
  "items": []
}
```

---

## 9. 依赖规范

### 9.1 语义

- `dependencies` 用于决定加载顺序。
- 仅对“已启用插件集合”做排序。

### 9.2 当前运行时注意点

1. 依赖不会自动补启（即声明依赖 != 自动启用依赖）。
2. `required: true` 的插件不能被关闭。
3. 依赖缺失会在校验阶段报错。

---

## 10. 版本与兼容策略（扩展核心）

### 10.1 插件版本

- `version` 表示插件自身迭代（建议 semver）。

### 10.2 规范版本（建议新增，非强制）

```yaml
spec_version: "1.0"
```

- 未声明时默认按 `1.0` 处理。
- 后续破坏性变更通过 `spec_version` 主版本升级体现。

### 10.3 引擎兼容范围（可选）

```yaml
compatibility:
  min_engine: "0.1.0"
  max_engine: "0.x"
```

当前引擎可忽略该字段，但建议保留，为后期精细兼容做准备。

### 10.4 向后兼容规则

1. 新增字段必须可忽略。
2. 旧字段废弃需至少跨一个 minor 周期。
3. 删除字段前先提供替代字段和迁移说明。

---

## 11. 校验规则

当前推荐校验（与实现对齐）：

1. 存在 `PLUGIN.md`
2. frontmatter 可解析
3. 必需字段齐全
4. `name` 与目录名一致
5. `name` 格式合法（小写字母/数字/连字符）
6. `dependencies` 引用存在
7. `hooks` 声明脚本路径存在（如声明）
8. `prompt.template` 路径存在（如声明）

---

## 12. 扩展流程（建议工作流）

### 12.1 新能力先走扩展命名空间

先在 `extensions.<namespace>` 里试验，不污染标准字段。

### 12.2 稳定后再标准化

扩展能力至少经过：

1. 一个真实插件落地
2. 一组回归测试
3. 向后兼容评审

再提升为标准字段。

### 12.3 扩展降级策略

若运行时不认识某能力，插件应仍可在“无该能力”下运行（仅损失增强功能）。

---

## 13. 参考模板

### 13.1 最小可用插件

```yaml
---
name: my-plugin
description: 示例插件
type: gameplay
required: false
version: "1.0.0"
prompt:
  position: pre-response
  priority: 90
  template: prompts/instruction.md
---
```

### 13.2 可扩展插件模板

```yaml
---
name: advanced-plugin
description: 带扩展命名空间的插件
type: gameplay
required: false
version: "2.1.0"
spec_version: "1.0"
dependencies:
  - core-blocks
prompt:
  position: world-state
  priority: 60
  template: prompts/state.md
blocks:
  advanced_result:
    instruction: |
      ...
    handler:
      actions:
        - type: storage_write
          key: latest
    ui:
      component: card
      title: "{{ title }}"
extensions:
  myteam:
    ranking_mode: weighted
    telemetry:
      enabled: true
---
```

---

## 14. 实施建议

1. 新插件优先复用 `core-blocks` 的基础 block 类型。
2. 自定义 block 先用 schema UI 落地，必要时再加 custom renderer。
3. 每个插件至少提供一个有效 `instruction` 示例 block。
4. 插件正文只写“当前运行时真实生效”的能力，保留能力单独标注为 Reserved。

---

文档版本：v1.0  
更新日期：2026-02-16
