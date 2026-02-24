# AI GameStudio 插件生态架构 V3

> 本文是 V3 架构实现说明。V3 采用 **Plugin Agent + Progressive Disclosure** 架构：
> 主 LLM 只输出纯叙事，独立的 Plugin Agent 通过 function calling 按需加载插件、操作游戏数据、输出结构化 block。
>
> **当前状态：V3 完整实现，所有内置插件已迁移至分组目录。**
>
> 配套规范：`docs/PLUGIN-SPEC.md`（实现级字段定义与完整示例）。

---

## 1. 设计原则（冻结决策）

以下 8 条决策已冻结，作为实现约束：

1. **主 LLM 纯叙事**：主 LLM 只输出故事文本，不输出任何 `json:xxx` block 或结构化数据。
2. **Plugin Agent 负责游戏机制**：独立的 Plugin Agent（LLM + function calling）分析叙事后决定触发哪些插件、输出哪些 block。
3. **Progressive Disclosure（渐进式披露）**：Plugin Agent 启动时只知道插件 name + description（Level 1），需要时调用 `load_plugin()` 获取完整指令（Level 2），再按需 `execute_script()` 或 `db_*`（Level 3）。
4. **Prompt injection 保留为上下文机制**：PromptBuilder 6 位置仍然存在，但仅用于向主 LLM 注入叙事上下文（角色状态、世界信息、记忆等），不注入 block 格式说明。
5. **manifest.json 是唯一机器事实源**：依赖、权限、能力、blocks、events、storage、i18n 全部声明在 manifest.json 中。
6. **插件独立于核心代码**：插件开发者只需编写 PLUGIN.md + manifest.json（+ 可选脚本），无需了解后端代码。
7. **最小必需文件区分内外**：builtin 插件仅需 `PLUGIN.md` + `manifest.json`；external 插件需额外 `README.md` + `schemas/`。
8. **所有自带插件双语**：必须同时提供 `i18n.en` + `i18n.zh`。

---

## 2. 插件合并映射（V1 → V3）

### 2.1 插件合并

V3 将 18 个旧扁平插件合并为 10 个分组插件：

| 新插件 | 合并自 | 分组 | supersedes |
|--------|--------|------|------------|
| `database` | `database`（重构） | core | — |
| `state` | `core-blocks` + `character` | core | `core-blocks`, `character` |
| `event` | `core-blocks`(event) + `quest` | core | `quest` |
| `memory` | `memory` + `archive` + `auto-compress` | core | `archive`, `auto-compress` |
| `guide` | `auto-guide` + `choices` | narrative | `auto-guide`, `choices` |
| `codex` | `codex` | narrative | — |
| `image` | `story-image` | narrative | `story-image` |
| `combat` | `combat` + `skill-check` + `dice-roll` + `status-effect` | rpg-mechanics | `skill-check`, `dice-roll`, `status-effect` |
| `inventory` | `inventory` + `loot` | rpg-mechanics | — |
| `social` | `relationship` + `faction` | rpg-mechanics | `relationship`, `faction` |

旧插件已移至 `plugins/backup/`（gitignored，不参与发现）。

### 2.2 架构变化（V2 → V3）

| V2 机制 | V3 去向 | 变更类型 |
|---------|---------|---------|
| 主 LLM 输出 `json:xxx` blocks | 主 LLM 纯叙事，Plugin Agent 通过 `emit_block()` 输出 | **替换** |
| `json:plugin_use` 协议 | Plugin Agent 的 `execute_script()` 工具 | **替换** |
| `block_parser.extract_blocks()` 从 LLM 响应提取 | blocks 来自 Plugin Agent 工具调用 | **替换** |
| `blocks.instruction` 字段 | 移除（Plugin Agent 看 PLUGIN.md 自行判断） | **移除** |
| pre-response 注入 block 格式说明 | pre-response 仅注入叙事上下文 | **简化** |
| `PLUGIN_PIPELINE` 配置项 | 移除（唯一使用 Plugin Agent） | **移除** |
| `process_message` / `process_message_v3` | 合并为唯一 `process_message` | **合并** |
| V1 回退（无 manifest.json） | 移除（所有插件必须有 manifest.json） | **移除** |
| PromptBuilder 6 位置注入 | 保留（仅注入叙事上下文） | 保留 |
| PluginStorage | 保留 | 保留 |
| PluginEventBus | 保留 | 保留 |
| `dispatch_block()` | 保留（处理 Plugin Agent emit 的 blocks） | 保留 |
| `manifest.json` 事实源 | 保留（新增 `supersedes`/`default_enabled`/`i18n` 字段） | **增强** |

---

## 3. 组件架构

### 3.1 核心组件

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| **Plugin Agent** | `backend/app/services/plugin_agent.py` | 独立 LLM + function calling，分析叙事后触发游戏机制 |
| **Plugin Tools** | `backend/app/core/plugin_tools.py` | Plugin Agent 可用工具定义（list/load/emit/execute/db_*） |
| PluginEngine | `backend/app/core/plugin_engine.py` | 插件发现（支持分组目录）、加载、prompt 注入配置 |
| ManifestLoader | `backend/app/core/manifest_loader.py` | manifest.json 解析 + schemas/ 加载 |
| PromptBuilder | `backend/app/core/prompt_builder.py` | 6 位置 prompt 组装（仅叙事上下文） |
| GameDB | `backend/app/core/game_db.py` | 游戏数据库抽象（kv/graph/log） |

### 3.2 Block 处理组件

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| dispatch_block | `backend/app/core/block_handlers.py` | 处理 Plugin Agent emit 的 blocks |
| block_validation | `backend/app/core/block_validation.py` | schema 校验 |
| PluginEventBus | `backend/app/core/event_bus.py` | 请求级事件总线 |
| DeclarativeBlockHandler | `backend/app/core/block_handlers.py` | 声明式 handler（storage_write / emit_event） |

### 3.3 脚本执行组件

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| ScriptRunner | `backend/app/core/script_runner.py` | Python 脚本 subprocess 执行 |
| CapabilityExecutor | `backend/app/core/capability_executor.py` | 校验 capability 声明 → 分发执行 |
| AuditLogger | `backend/app/core/audit_logger.py` | 脚本执行审计日志 |

### 3.4 存储与状态

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| GameStateManager | `backend/app/core/game_state.py` | DB 操作（messages / characters / world） |
| PluginStorage | `backend/app/models/plugin_storage.py` | 插件键值存储 |

---

## 4. 执行流程

### 4.1 完整 Turn 处理流

```
chat_service.process_message(session_id, user_content)
  │
  ├─ 1. build_turn_context()
  │     ├─ 解析 enabled_plugins（含 supersedes 逻辑）
  │     ├─ 加载 archive_context / memories / compression_summary
  │     └─ 加载 runtime_settings
  │
  ├─ 2. 保存 user message
  │
  ├─ 3. assemble_narrative_prompt(ctx, user_content)
  │     ├─ PluginEngine.get_prompt_injections(enabled_names, context)
  │     │     ├─ 读 manifest.json.prompt → {position, priority, template}
  │     │     ├─ 渲染 Jinja2 模板（或 PLUGIN.md body）
  │     │     └─ 返回 [{position, priority, content}, ...]
  │     │
  │     ├─ PromptBuilder.inject() × N
  │     │     位置 1: system     — world doc + global plugins
  │     │     位置 2: character  — character state + scene
  │     │     位置 3: world-state — game state + plugin state
  │     │     位置 4: memory     — long/short-term memory + archive
  │     │     位置 5: chat-history — recent messages
  │     │     位置 6: pre-response — narrative-only 指令（无 block 格式）
  │     │
  │     └─ PromptBuilder.build() → [{role, content}, ...]
  │
  ├─ 4. 流式调用主 LLM（纯叙事，无 tools）
  │     └─ yield chunk events → WebSocket → 前端
  │
  ├─ 5. 保存 assistant message + 更新 token 统计
  │
  ├─ 6. run_plugin_agent(narrative, game_state, enabled_plugins, ...)
  │     │
  │     ├─ 系统提示词 + 叙事文本 + 游戏状态
  │     │
  │     └─ 多轮 tool calling 循环（最多 10 轮）：
  │           ├─ LLM 选择工具 → list_plugins / load_plugin / emit_block / execute_script / db_*
  │           ├─ 执行工具 → 返回结果
  │           ├─ LLM 继续或结束
  │           └─ 收集所有 emit_block 的 blocks
  │
  ├─ 7. dispatch blocks
  │     ├─ 遍历 Plugin Agent emit 的 blocks
  │     ├─ dispatch_block() → handler actions / event bus / 转发前端
  │     └─ yield block events → WebSocket → 前端
  │
  ├─ 8. Auto archive（memory 插件启用时）
  │
  ├─ 9. Auto compress（memory 插件启用时，context_usage > threshold）
  │
  └─ 10. yield turn_end event
```

### 4.2 Plugin Agent 内部流程

```
Plugin Agent LLM（function calling）
  │
  ├─ 输入：系统提示 + 叙事文本 + 游戏状态快照
  │
  ├─ Round 1: list_plugins() → [{name, description}, ...]
  │     Plugin Agent 了解可用插件概览
  │
  ├─ Round 2: load_plugin("state") → {prompt, blocks, capabilities}
  │     Plugin Agent 获取完整指令，判断需要 emit 哪些 blocks
  │
  ├─ Round 3: emit_block("state_update", {...})
  │     同时可能调用 db_kv_set() 持久化
  │
  ├─ Round 4: load_plugin("guide") → {prompt, blocks, capabilities}
  │     获取 guide 插件指令
  │
  ├─ Round 5: emit_block("guide", {...})
  │
  └─ Round 6: 无更多工具调用 → 结束
```

### 4.3 Progressive Disclosure 层级

| 层级 | 何时加载 | Token 消耗 | 内容 |
|------|---------|-----------|------|
| Level 1 | Plugin Agent 启动时 | ~30 tokens/插件 | 仅 name + description |
| Level 2 | `load_plugin()` 时 | < 5k tokens | 完整 PLUGIN.md + blocks + capabilities |
| Level 3 | `execute_script()` 时 | 几乎为 0 | 脚本 subprocess 执行，结果 JSON 返回 |

---

## 5. Block 分类

### 5.1 Block 来源

V3 中所有 blocks 均由 Plugin Agent 的 `emit_block()` 工具产出。主 LLM 不输出任何 block。

### 5.2 Block 类型总表

| Block Type | 来源插件 | 后端 Handler | 前端 Renderer |
|-----------|---------|-------------|--------------|
| state_update | state | StateUpdateHandler (builtin) | 无（静默应用） |
| character_sheet | state | CharacterSheetHandler (builtin) | custom: character_sheet |
| scene_update | state | SceneUpdateHandler (builtin) | custom: scene_update |
| event | event | EventHandler (builtin) | 无（静默应用） |
| notification | state | 无（pass-through） | custom: notification |
| guide | guide | 无（pass-through） | custom: guide |
| codex_entry | codex | DeclarativeBlockHandler | custom: codex_entry |
| story_image | image | StoryImageHandler (builtin) | custom: story_image |
| dice_result | combat | DeclarativeBlockHandler | card (schema UI) |
| combat_start | combat | DeclarativeBlockHandler | custom: combat_start |
| combat_round | combat | DeclarativeBlockHandler | custom: combat_round |
| combat_end | combat | DeclarativeBlockHandler | custom: combat_end |
| item_update | inventory | DeclarativeBlockHandler | card (schema UI) |
| loot | inventory | DeclarativeBlockHandler | custom: loot |
| relationship_change | social | DeclarativeBlockHandler | custom: relationship_change |
| reputation_change | social | DeclarativeBlockHandler | custom: reputation_change |

### 5.3 Block 生命周期

```
Plugin Agent emit_block(type, data)
  → chat_service 收集到 blocks 列表
  → dispatch_block(block, context, declarations)
       ├─ validate_block_data(block, schema)
       ├─ handler.actions 执行（storage_write / emit_event / builtin）
       └─ yield → WebSocket → 前端 renderer
```

---

## 6. 安全模型

### 6.1 脚本执行

| 策略 | 规则 |
|------|------|
| 支持语言 | Phase 1 仅 Python |
| 超时 | 默认 5000ms，manifest 可声明覆盖（100-60000ms） |
| 文件系统 | 仅允许访问插件目录 + `data/` 目录 |
| 审计 | 每次执行记录 invocation_id / plugin / script / args / exit_code / duration_ms |

### 6.2 网络策略

| 插件类型 | 默认网络策略 |
|---------|------------|
| global | 允许联网 |
| gameplay | 禁止联网 |

### 6.3 存储隔离

插件存储通过 `PluginStorage` 表的 `(project_id, plugin_name, key)` 三元组隔离。

### 6.4 Plugin Agent 安全

- Plugin Agent 最多执行 10 轮工具调用（`MAX_TOOL_ROUNDS = 10`）
- Plugin Agent 只能操作当前 session 的数据
- `execute_script` 会校验插件是否启用、capability 是否声明

---

## 7. API

### 7.1 现有端点

| 端点 | 说明 |
|------|------|
| `GET /api/plugins` | 返回所有插件元数据（含 i18n / supersedes / default_enabled / capabilities） |
| `POST /api/plugins/{name}/toggle` | 切换插件启用状态 |
| `GET /api/plugins/enabled/{project_id}` | 获取项目启用插件列表 |
| `GET /api/plugins/block-schemas?project_id=...` | 获取 block schema |

### 7.2 导入与审计

| 端点 | 说明 |
|------|------|
| `POST /api/plugins/import/validate` | 校验待导入插件包 |
| `POST /api/plugins/import/install` | 安装外部插件 |
| `GET /api/plugins/{name}/audit` | 查询脚本执行审计日志 |

---

## 8. 前端影响

### 8.1 不变

- WebSocket 事件协议：`chunk` / `done` / `{block_type}` / `token_usage` / `notification` / `turn_end`
- Block renderer 注册系统：`registerBlockRenderer(type, Component)`
- sessionStore 的 pendingBlocks 机制

### 8.2 V3 变化

| 变更 | 说明 |
|------|------|
| Block 来源 | 所有 blocks 来自 Plugin Agent（不再从 LLM 响应文本中提取） |
| Plugin 类型定义 | 新增 supersedes / default_enabled / i18n 字段 |
| PluginPanel | 按用户语言显示 i18n 名称和描述 |

---

## 9. 实施状态

### Phase A：manifest.json 基础 ✅

1. ManifestLoader 实现（解析 manifest.json + schemas/）
2. PluginEngine 支持分组目录发现（`plugins/<group>/<plugin>/`）
3. 10 个新分组插件全部完成 manifest.json
4. `GET /api/plugins` 返回 manifest 级元数据

### Phase B：Plugin Agent ✅

1. Plugin Agent 实现（`plugin_agent.py`）
2. Plugin Tools 定义（`plugin_tools.py`）
3. GameDB 抽象层实现（`game_db.py`）
4. chat_service.process_message 集成 Plugin Agent

### Phase C：V1 → V3 清理 ✅

1. 移除 `PLUGIN_PIPELINE` 配置项
2. 合并 `process_message_v3` 为唯一 `process_message`
3. 清理 `assemble_prompt` 等 V1 遗留代码
4. 18 个旧插件移至 `plugins/backup/`（gitignored）
5. 所有新插件添加 `supersedes` 字段
6. 插件名引用更新（archive→memory, auto-compress→memory, story-image→image）
7. `_FORCE_TRIGGER_PROMPTS` 和 `DEFAULT_INIT_PROMPT` 适配纯叙事架构

### Phase D：生态扩展（部分）

- [x] 运行时设置（runtime_settings）
- [x] 插件 i18n（名称、描述、设置项）
- [x] `supersedes` 字段
- [x] `default_enabled` 字段
- [ ] 插件导出（zip/tarball）
- [ ] 多语言脚本支持（JavaScript）
- [ ] 项目级模板覆盖
- [ ] 插件市场基础设施

---

## 10. 代码路径映射

### 10.1 后端核心

| 文件 | 职责 |
|------|------|
| `backend/app/services/plugin_agent.py` | Plugin Agent：叙事分析 + 多轮 tool calling |
| `backend/app/core/plugin_tools.py` | Plugin Agent 工具定义（list/load/emit/execute/db_*） |
| `backend/app/core/game_db.py` | 游戏数据库抽象（kv/graph/log） |
| `backend/app/services/chat_service.py` | process_message：叙事 LLM + Plugin Agent 集成 |
| `backend/app/services/prompt_assembly.py` | assemble_narrative_prompt（纯叙事 prompt） |
| `backend/app/services/turn_context.py` | build_turn_context（构建回合上下文） |

### 10.2 插件引擎

| 文件 | 职责 |
|------|------|
| `backend/app/core/plugin_engine.py` | 插件发现（含分组）、加载、prompt 注入 |
| `backend/app/core/manifest_loader.py` | manifest.json 解析 + schemas/ 加载 |
| `backend/app/core/block_handlers.py` | block dispatch + declarative handler |
| `backend/app/core/block_validation.py` | block schema 校验 |
| `backend/app/core/capability_executor.py` | capability 执行分发 |
| `backend/app/core/script_runner.py` | Python 脚本 subprocess 执行 |
| `backend/app/core/audit_logger.py` | 脚本执行审计日志 |
| `backend/app/services/plugin_service.py` | get_enabled_plugins（含 supersedes 逻辑） |

### 10.3 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/blockRenderers/` | Block renderer 组件 |
| `frontend/src/components/plugins/` | PluginPanel 等插件管理 UI |
| `frontend/src/blockRenderers.ts` | registerBlockRenderer 注册 |

---

## 11. 假设与默认值

1. 首期脚本语言仅支持 Python。
2. 首期不做插件导出。
3. 首期不做项目级模板覆盖。
4. 所有自带插件必须提供 `i18n.en` + `i18n.zh`。
5. Plugin Agent 最多执行 10 轮工具调用。
6. 主 LLM 不输出任何 block，所有 block 由 Plugin Agent 产出。
7. 旧插件通过 `supersedes` 机制自动禁用，数据 namespace key 保持不变（兼容已有数据）。

---

文档版本：v3.0
更新日期：2026-02-24
