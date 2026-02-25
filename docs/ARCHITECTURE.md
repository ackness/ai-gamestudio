# System Architecture

AI GameStudio 当前采用双阶段回合架构：

- 阶段 A：主 LLM 只负责叙事文本。
- 阶段 B：Plugin Agent 负责机制执行和结构化 block 输出。

插件规范为单版本 v1（`schema_version: "1.0"`），无 v2/v3 分支逻辑。

核心与插件边界：

- 核心负责阶段编排（Hook）、状态与存储、统一事件协议、基础 UI 渲染能力。
- 插件负责“在 Hook 上扩展行为”，并可通过 block + UI schema 同时影响后端副作用与前端呈现。

## 1. 关键模块映射

| 模块 | 代码位置 | 职责 |
|---|---|---|
| 回合编排 | `backend/app/services/chat_service.py` | 主流程、阶段切换、事件流、block 分发 |
| 上下文装配 | `backend/app/services/turn_context.py` | 会话/项目/状态/插件与运行时设置聚合 |
| 叙事提示组装 | `backend/app/services/prompt_assembly.py` | 叙事模式 prompt（内部使用 `PromptBuilder`） |
| 插件代理 | `backend/app/services/plugin_agent.py` | 插件并行调用、工具循环、block 收集 |
| Hook 契约 | `backend/app/core/plugin_hooks.py` | 核心阶段 Hook 常量与归一化规则 |
| Trigger 策略 | `backend/app/core/plugin_trigger.py` | 插件/Block 触发策略归一化与校验 |
| 插件引擎 | `backend/app/core/plugin_engine.py` | 发现/加载/校验插件，提取 block/capability 声明 |
| Manifest 解析 | `backend/app/core/manifest_loader.py` | `manifest.json` v1 校验与 metadata 归一化 |
| Block 校验 | `backend/app/core/block_validation.py` | block 数据 schema 校验 |
| Block 调度 | `backend/app/core/block_handlers.py` | builtin + 声明式 handler 执行 |
| 插件启用策略 | `backend/app/services/plugin_service.py` | required/default/world/user/deps/supersedes 合并 |
| 运行时设置 | `backend/app/services/runtime_settings_service.py` | schema 聚合、值合并、scope 校验 |

## 2. 标准回合执行序列（`process_message`）

1. `build_turn_context()` 加载会话、项目、角色、场景、事件、插件启用集、runtime settings。
2. `assemble_narrative_prompt()` 构建叙事 prompt（不含 block 指令）。
3. 主 LLM 流式输出文本（`chunk` 事件），结束后发 `done`。
4. 落库 assistant 叙事消息，更新 token/cost 统计（`token_usage`）。
5. 进入插件阶段（`phase_change: plugins`）。
6. `run_plugin_agent(hook="post_narrative")` 对声明该 Hook 的插件并行执行工具调用，流式发 `plugin_progress`。
7. 插件完成后发 `plugin_summary`，阶段切到 `phase_change: complete`。
8. 对每个 block：`validate_block_data()` -> `dispatch_block()` -> 发送前端事件。
9. 持久化消息 metadata 中的 blocks，更新 `plugin_trigger_counts`。
10. 若启用 `memory`：尝试自动归档与上下文压缩，最后发 `turn_end`。

## 3. Plugin Agent 执行模型

- 并发粒度：按插件并发（`asyncio.gather`）。
- 每插件工具轮数上限：`MAX_TOOL_ROUNDS = 8`。
- 工具契约固定 6 个：
1. `emit`
2. `db_read`
3. `db_log_append`
4. `db_log_query`
5. `db_graph_add`
6. `execute_script`
- 结构化输出统一由 `emit.items` 产生，核心按标准 envelope 校验与分发。

- 触发上限：若插件配置 `max_triggers` 且达到会话计数，将跳过该插件本轮执行。
- Hook 过滤：插件可通过 `manifest.hooks` 声明参与阶段；核心按当前阶段只调度匹配 Hook 的插件。
- 触发策略：插件可通过 `manifest.trigger` 声明 `always / interval / manual`。
  - 示例：`memory` 可设为每 3 回合执行一次；
  - 示例：`image` 可设为 `manual`，仅走前端按钮触发的图片生成入口。
- 指令可见性：对 `once_per_session` 等受限 block，核心会在后续轮次从插件 block 指令中隐藏对应提示，减少幻觉与 token 消耗。
- 产物汇总：返回 `blocks + plugin_summary`，其中 summary 含 `rounds/tool_calls/blocks_emitted/plugins_run`。

## 4. 插件发现、加载与启用

### 4.1 目录发现

`PluginEngine` 同时支持：

- 平铺目录：`plugins/<plugin>/`
- 分组目录：`plugins/<group>/<plugin>/`（`plugins/<group>/group.json`）

### 4.2 必需文件

每个插件必须有：

- `manifest.json`（机器契约）
- `PLUGIN.md`（LLM 行为说明）

`manifest.json` 仅接受 `schema_version: "1.0"`。

### 4.3 启用集合计算

`get_enabled_plugins()` 统一合并：

1. `required=true`
2. world frontmatter `plugins`
3. `default_enabled=true`
4. 用户显式开关
5. 依赖自动补全
6. `supersedes` 抑制（显式用户启用可覆盖抑制）

## 5. Block 管道细节

- 生成来源：`emit.items`。
- 校验：优先插件声明 schema（或 builtin schema）+ 基础约束。
- block 触发策略：支持 `once_per_session`（如 `character_sheet`）。
- 调度顺序：
1. builtin handler
2. manifest 声明式 handler（如 `storage_write`/`emit_event`/`builtin`）
3. 无 handler 时透传前端

- 基础设施 block（如 `state_update`）会执行但不下发前端。
- 冲突抑制规则（当前实现）：
1. 若存在 `character_sheet`，抑制 `guide/choices/auto_guide`
2. 若已存在 player 角色，抑制 `character_sheet`

## 6. Runtime Settings 架构

- 来源：启用插件 `manifest.extensions.runtime_settings`。
- 归一化：`manifest_to_metadata()` 会把旧写法 `settings[]` 自动转换为 `fields{}`。
- 存储命名空间：`plugin_name = "runtime-settings"`。
- 存储键：
1. 项目级：`project`
2. 会话级：`session:<session_id>`

- 解析结果包含 `values/by_plugin/project_overrides/session_overrides/schema_fields`。

## 7. 记忆与压缩路径

- `memory` 插件负责自动归档入口（`maybe_auto_archive_summary`）与压缩阈值控制。
- 当前压缩摘要存储仍使用历史命名空间键：
1. plugin: `auto-compress`
2. keys: `compression-summary` / `compression-state`

该键路径是当前实现行为，不代表多版本插件协议。

## 8. 前端执行链路

前端主链路由 `GamePanel` + `useGameWebSocket` + Zustand store 组成：

- 入口组件：`frontend/src/components/game/GamePanel.tsx`
- 连接与事件分发：`frontend/src/hooks/useGameWebSocket.ts`
- 用户动作发送：`frontend/src/hooks/useGameActions.ts`
- 传输层：`frontend/src/services/websocket.ts`

### 8.1 传输模式

- 默认 WebSocket。
- 若检测到后端存储非持久（如 Vercel 场景），自动降级 HTTP command 模式。
- 两种模式都复用同一套事件类型（`chunk/done/plugin_progress/plugin_summary/turn_end/...`）。

### 8.2 事件到状态映射

- `chunk/done` -> `sessionStore` 流式消息状态。
- `state_update/scene_update/event` -> `gameStateStore` 与场景状态。
- `plugin_progress/plugin_summary` -> `sessionStore.pluginProgress/lastPluginSummary`。
- `token_usage` -> `tokenStore`。
- `message_blocks_updated` -> 原消息 block 原位更新（用于 retrigger 等场景）。

### 8.3 Block 渲染优先级

`frontend/src/services/blockRenderers.ts` 按以下顺序解析渲染器：

1. 显式注册渲染器（`frontend/src/blockRenderers.ts`）
2. 插件 schema 驱动的 `GenericBlockRenderer`
3. 未匹配则退回 fallback JSON 展示

## 9. API 面向层

插件相关 API：

- `GET /api/plugins`
- `POST /api/plugins/{name}/toggle`
- `GET /api/plugins/enabled/{project_id}`
- `GET /api/plugins/block-schemas`
- `GET /api/plugins/block-conflicts`
- `POST /api/plugins/import/validate`
- `POST /api/plugins/import/install`
- `GET /api/plugins/{name}/detail`
- `GET /api/plugins/{name}/audit`

运行时设置 API：

- `GET /api/runtime-settings/schema`
- `GET /api/runtime-settings`
- `PATCH /api/runtime-settings`

## 10. 验证命令

```bash
mise run plugin:list
mise run plugin:validate
mise run plugin:test:list
mise run plugin:test:dry-run
```

## 11. 版本声明

本架构文档与当前主干代码同步，插件系统按单版本 v1 维护。
