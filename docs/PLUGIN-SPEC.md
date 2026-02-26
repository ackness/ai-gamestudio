# AI GameStudio Plugin Spec v1

本文档是当前唯一有效的插件规范（`schema_version: "1.0"`）。
不存在 v2/v3 分支，也不保留旧版 fallback 逻辑。

## 1. 基本约束

- 单版本：仅支持 `schema_version = "1.0"`。
- 单契约：每个插件必须同时提供 `manifest.json` 与 `PLUGIN.md`。
- 单输出模型：结构化输出统一通过工具 `emit` 返回。
- 单声明源：插件可输出类型统一由 `manifest.outputs` 声明。

## 2. 目录布局

推荐分组布局：

```text
plugins/
  <group>/
    group.json
    <plugin>/
      manifest.json
      PLUGIN.md
      prompts/
      scripts/
      schemas/
```

兼容平铺布局：

```text
plugins/
  <plugin>/
    manifest.json
    PLUGIN.md
```

## 3. manifest.json

### 3.1 必填字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `schema_version` | string | 必须是 `"1.0"` |
| `name` | string | 与目录名一致；小写字母/数字/短横线 |
| `version` | string | 插件版本 |
| `type` | string | `global` 或 `gameplay` |
| `required` | boolean | 是否强制启用 |
| `description` | string | 插件说明 |

### 3.2 常用可选字段

| 字段 | 说明 |
|---|---|
| `dependencies` | 依赖插件列表 |
| `default_enabled` | 默认启用 |
| `supersedes` | 抑制其他插件 |
| `prompt` | 提示词模板配置（`position/priority/template`） |
| `outputs` | 可输出类型声明（核心字段） |
| `capabilities` | 能力声明（可映射脚本） |
| `extensions.runtime_settings` | 运行时参数声明 |
| `hooks` | 插件挂载阶段（默认 `post_model_output`） |
| `trigger` | 插件触发策略（`always/interval/manual`） |
| `max_triggers` | 每会话执行上限 |
| `storage` | 插件持久化键声明 |
| `events` | 事件声明（emit/listen） |

## 4. Hook 与 Trigger

### 4.1 Hook（阶段挂载）

当前支持：

- `pre_model_input`
- `post_model_output`（默认）
- `frontend_action`
- `post_dispatch`

兼容别名（历史写法）：

- `pre_narrative` -> `pre_model_input`
- `post_narrative` -> `post_model_output`
- `ui_action` -> `frontend_action`

### 4.2 Trigger（插件触发策略）

- `always`：每次进入 Hook 都执行
- `interval`：每 N 回合执行一次
- `manual`：仅手动触发，不参与自动调度（默认主回合链路不会自动运行）

示例：

```json
{
  "trigger": {
    "mode": "interval",
    "interval_turns": 3,
    "interval_setting_key": "trigger_interval_turns"
  }
}
```

## 5. Prompt 模板（Jinja2）

插件模板来自 `manifest.prompt.template`，可通过 `PluginEngine.get_prompt_injections()` 渲染。
当前主叙事链路默认不注入插件模板（保持主模型纯叙事）；插件逻辑由插件模型独立处理。

模板应只做展示逻辑（`if/for/default`），不要承载业务计算。

运行时核心上下文（推荐使用）：

- `core`：会话、角色、场景、世界状态等基础上下文
- `events`：当前事件上下文
- `storage`：插件存储视图（含 `flat/by_plugin`）
- `runtime_settings`：按插件聚合的设置
- `plugin_context`：核心预计算的插件专用上下文

兼容别名（现有模板可继续使用）：

- `player / npcs / current_scene / scene_npcs`
- `world_state / active_events`
- `memories / archive / compression_summary / story_images`
- `settings`（当前插件 runtime settings）
- `plugin_storage`（当前插件 storage）

## 6. outputs（结构化输出声明）

`manifest.outputs` 定义插件允许输出的类型。每个类型可声明：

- `instruction` / `instruction_file`
- `schema`（必填，建议 `additionalProperties: false`）
- `handler`
- `ui`
- `requires_response`
- `trigger`（例如 `once_per_session`）

重要约束：

- `emit.items[].type` 必须是 `manifest.outputs` 里声明过的类型。
- 未声明类型会被核心忽略，不会进入分发链路。
- 每个输出类型都应提供清晰 `schema`，用于提示、校验与前端契约对齐。
- Agent Prompt 会基于每个输出的 schema 自动追加最小调用模板与简短示例，以提高一次工具调用成功率。

## 7. 统一输出工具 emit

插件运行时统一使用 `emit`，可一次完成：

- `writes`：KV 写入
- `logs`：日志追加
- `items`：结构化输出列表
- `meta`：默认元信息（并入每个 item）

严格约束：

- `emit` 采用严格字段校验，不做自动补字段兼容。
- `items` 中任一结构化项字段不合法（如 `character_sheet.data.name` 为空、`scene_update(action=move)` 缺少 `name`）会返回 `status=error`。
- `status=error` 时本次 `emit` 视为失败，不应依赖“自动修正”；模型需要按错误提示重试。

标准输出项结构：

```json
{
  "id": "out_xxx",
  "version": "1.0",
  "type": "choices",
  "data": {},
  "meta": {
    "plugin": "guide",
    "turn_id": "turn_xxx",
    "group_id": "grp_xxx",
    "created_at": "2026-02-25T00:00:00Z"
  },
  "status": "done"
}
```

`status` 允许值：

- `queued`
- `generating`
- `done`
- `failed`

## 8. Plugin Agent 工具集（当前实现）

当前固定工具：

1. `emit`
2. `db_read`
3. `db_log_append`
4. `db_log_query`
5. `db_graph_add`
6. `execute_script`

## 9. 工具错误返回契约

当工具调用失败时，返回结构化错误，便于模型自我修复与重试：

```json
{
  "ok": false,
  "error": {
    "tool": "emit",
    "code": "INVALID_ARGUMENTS",
    "message": "arguments must be a JSON object",
    "details": "...",
    "retryable": true
  },
  "text": "TOOL_ERROR [emit] INVALID_ARGUMENTS: ... | action: fix arguments/state and retry this tool call."
}
```

## 10. capabilities（脚本能力）

脚本能力示例：

```json
{
  "dice.roll": {
    "description": "Roll dice",
    "implementation": {
      "type": "script",
      "script": "scripts/roll.py",
      "timeout_ms": 5000
    },
    "result_block_type": "dice_result"
  }
}
```

安全约束：

- 脚本路径必须位于插件目录内。
- 越界路径（`../`）会在校验时失败。

## 11. Runtime Settings

声明入口：

```json
{
  "extensions": {
    "runtime_settings": {
      "fields": {
        "option_name": {
          "type": "enum",
          "default": "x"
        }
      }
    }
  }
}
```

核心会将其解析为：

- `values`（扁平键，如 `guide.option_count`）
- `by_plugin`（按插件分组）

## 12. 校验与测试

推荐校验流程：

```bash
mise run plugin:list
uv run python -m backend.app.core.plugin_engine validate plugins/
```

插件集成测试：

```bash
uv run python scripts/test_plugin_agent.py --all
```

`--all` 模式默认并行执行（可通过 `-j` 调整并发）。
