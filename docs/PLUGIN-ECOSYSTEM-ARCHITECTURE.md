# Plugin Ecosystem Architecture (v1)

本文档描述当前插件系统在后端、前端与测试链路中的真实运行方式。

## 1. 设计目标

- 核心只提供阶段 Hook、调度、校验、分发与基础渲染契约。
- 插件负责业务扩展（可影响模型输入/输出、前端交互、状态更新）。
- 结构化结果统一通过 `emit` 工具返回，避免模型直接输出漂移 JSON。

## 2. 当前插件版图

### 2.1 core

- `database`（required）
- `state`（required）
- `event`（required）
- `memory`（default_enabled）

### 2.2 narrative

- `guide`（default_enabled）
- `codex`
- `image`（default_enabled）

### 2.3 rpg-mechanics

- `combat`
- `inventory`
- `social`

## 3. 核心组件

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `PluginEngine` | `backend/app/core/plugin_engine.py` | 发现/加载/校验插件；渲染 prompt 模板；提取输出与能力声明 |
| `ManifestLoader` | `backend/app/core/manifest_loader.py` | `manifest.json` v1 解析与归一化 |
| `plugin_hooks` | `backend/app/core/plugin_hooks.py` | Hook 常量与归一化 |
| `plugin_trigger` | `backend/app/core/plugin_trigger.py` | 插件级与输出级触发策略 |
| `turn_context` | `backend/app/services/turn_context.py` | 构建叙事回合上下文（含 storage/runtime settings） |
| `prompt_assembly` | `backend/app/services/prompt_assembly.py` | 组装叙事 Prompt（不注入插件模板） |
| `plugin_agent` | `backend/app/services/plugin_agent.py` | 回合后并行执行插件工具调用 |
| `plugin_tools` | `backend/app/core/plugin_tools.py` | 定义平台工具（`emit` 等） |
| `block_handlers` | `backend/app/core/block_handlers.py` | 校验与分发结构化输出 |

## 4. 两阶段运行链路

### 4.1 叙事阶段（Narrative LLM）

1. `build_turn_context()` 聚合角色、场景、世界状态、事件、storage、runtime settings。
2. `assemble_narrative_prompt()` 仅注入叙事所需的世界文档、场景、角色、历史消息。
3. 主模型输出纯叙事文本（不要求结构化输出）。

### 4.2 插件阶段（Plugin Agent）

1. `run_plugin_agent()` 按 Hook + Trigger 过滤插件。
2. 插件并行执行（`asyncio.gather`），每插件最多 `MAX_TOOL_ROUNDS`。
3. 插件通过工具调用产生副作用与结构化输出：
   - 状态写入：`emit.writes / emit.logs`
   - 前端输出：`emit.items`
4. 输出进入 `dispatch_block()`：
   - 基础设施输出（如 `state_update`）仅后端处理
   - 前端可见输出按 renderer/schema 渲染

## 5. Prompt 上下文契约（Jinja2）

`PluginEngine.get_prompt_injections()` 支持 Jinja2 模板渲染能力，但默认主叙事链路不启用插件模板注入。
该能力用于插件开发/调试或未来可选链路，不影响当前双模型主架构。

模板可使用统一上下文：

- `core`
- `events`
- `storage`（含 `flat` 与 `by_plugin`）
- `runtime_settings`
- `plugin_context`

同时提供兼容别名（如 `player`, `current_scene`, `plugin_storage`, `settings`）。

约束：

- Jinja2 只负责展示层逻辑（条件/循环/格式化）。
- 业务计算与状态变更必须通过工具执行。

## 6. 输出与工具契约

### 6.1 工具集（固定）

1. `emit`
2. `db_read`
3. `db_log_append`
4. `db_log_query`
5. `db_graph_add`
6. `execute_script`

### 6.2 输出白名单

- 插件只能输出 `manifest.outputs` 中声明的类型。
- 每个 `manifest.outputs.<type>` 都应声明明确 schema，作为提示和运行时校验基准。
- 插件 Agent 在构造输出提示时，会按 schema 自动附带最小调用模板与单行示例，减少无效工具调用。
- 未声明类型会被忽略，不会进入分发。
- `emit.items` 采用严格字段校验：关键字段缺失/为空会直接返回错误并要求模型重试。

### 6.3 错误反馈（面向模型可重试）

工具失败时返回结构化错误与可读文本，例如：

```json
{
  "ok": false,
  "error": {
    "tool": "execute_script",
    "code": "SCRIPT_EXECUTION_FAILED",
    "message": "...",
    "retryable": true
  },
  "text": "TOOL_ERROR [execute_script] ... | action: fix arguments/state and retry this tool call."
}
```

这使模型可以根据错误位置（工具名/错误码）进行自修复重试。

## 7. 前端消费模型

前端统一消费标准输出 envelope：

```json
{
  "id": "out_xxx",
  "version": "1.0",
  "type": "choices",
  "data": {},
  "meta": {},
  "status": "done"
}
```

渲染策略：

- 先走 `renderer_name`（自定义组件）
- 再走 schema 渲染
- 最后 JSON fallback

## 8. 测试链路

### 8.1 后端测试

- `backend/tests/test_plugin_engine.py`
- `backend/tests/test_manifest_integration.py`
- `backend/tests/test_plugin_agent_hooks.py`
- `backend/tests/test_chat_service.py`

### 8.2 插件集成脚本

```bash
uv run python scripts/test_plugin_agent.py --all
```

说明：

- `--all` 模式默认并行执行（自动设置并发，默认上限 4）。
- 可用 `-j` 自定义并发。
- 脚本与后端一致：`emit` 仅接受声明过的输出类型。

## 9. 可扩展性原则

- 扩展插件能力优先走 `manifest` 声明与工具契约，不在核心写死业务分支。
- 插件之间通过结构化状态与事件协作，不依赖隐式字符串协议。
- 新增前端 UI 类型时，优先新增 `type + renderer/schema`，无需改模型输出格式。
