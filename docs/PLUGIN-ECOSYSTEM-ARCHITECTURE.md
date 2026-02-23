# AI GameStudio 插件生态架构 V2

> 本文是 V2 架构实现说明。V2 在 V1 基础上引入 `manifest.json` 事实源、`json:plugin_use` 统一调用协议和脚本执行能力，同时保留 V1 的 PromptBuilder 6 位置注入和 `json:xxx` Direct Block 体系不变。
>
> **当前状态：V2 完整实现，所有内置插件已完成 manifest.json 迁移。**
>
> 配套规范：`docs/PLUGIN-SPEC.md`（实现级字段定义与完整示例）。

---

## 1. 设计原则（冻结决策）

以下 7 条决策已冻结，作为实现约束：

1. **Prompt injection 是一等机制**：PromptBuilder 6 位置（system / character / world-state / memory / chat-history / pre-response）不变；`manifest.json.prompt` 承载 position / priority / template。
2. **`json:plugin_use` 是唯一调用协议**：LLM 需要后端执行能力时统一输出 `json:plugin_use`；脚本执行是 capability 的 implementation 细节，不暴露 `json:plugin_script` 给 LLM。
3. **Direct Output Blocks 与 Capability Invocation Blocks 分离**：LLM 直接输出的 `json:xxx` blocks（state_update / notification / choices 等）走 V1 既有流程；`json:plugin_use` 由后端执行后产出 result blocks。
4. **manifest.json 接管所有机器元数据**：PLUGIN.md frontmatter 只保留 LLM 专有字段（name / version / description / when_to_use / avoid_when / capability_summary）。
5. **when_to_use / avoid_when 是 LLM 提示词，不是规则引擎**：没有 Rule Matcher，LLM 在 pre-response 指令中看到激活条件后自行判断。
6. **最小必需文件区分内外**：builtin 插件仅需 `PLUGIN.md` + `manifest.json`；external 插件需额外 `README.md` + `schemas/`。
7. **运行时端点不独立暴露**：`plugin_use` 在 `chat_service.process_message()` 的 WebSocket 流中执行，不暴露独立 HTTP API。

---

## 2. V1 → V2 完整迁移映射表

### 2.1 机制迁移

| V1 机制 | V2 去向 | 变更类型 |
|---------|---------|---------|
| PLUGIN.md frontmatter `name/description/type/required` | `manifest.json` 顶层字段 | 移动 |
| PLUGIN.md frontmatter `version` | `manifest.json.version` | 移动 |
| PLUGIN.md frontmatter `dependencies` | `manifest.json.dependencies` | 移动 |
| PLUGIN.md frontmatter `prompt` (position/priority/template) | `manifest.json.prompt` | 移动 |
| PLUGIN.md frontmatter `blocks` | `manifest.json.blocks` | 移动 |
| PLUGIN.md frontmatter `events` | `manifest.json.events` | 移动 |
| PLUGIN.md frontmatter `storage` | `manifest.json.storage` | 移动 |
| PLUGIN.md frontmatter `extensions` | `manifest.json.extensions` | 移动 |
| PLUGIN.md body（Markdown 正文） | 不变，仍作为 prompt 内容注入 | 保留 |
| PluginEngine.discover() | 增强：优先读 manifest.json，回退 PLUGIN.md | 增强 |
| PluginEngine.load() | 增强：合并 manifest + PLUGIN.md | 增强 |
| PluginEngine.get_prompt_injections() | 不变，从 manifest.prompt 读取配置 | 保留 |
| PluginEngine.get_block_declarations() | 增强：从 manifest.blocks 读取，含 schema 文件引用 | 增强 |
| block_parser.extract_blocks() | 不变 | 保留 |
| block_handlers.dispatch_block() | 增强：新增 plugin_use 分支 | 增强 |
| block_validation.validate_block_data() | 增强：支持 schemas/ 文件加载 | 增强 |
| chat_service.process_message() | 增强：plugin_use block 触发 capability 执行 | 增强 |
| event_bus (PluginEventBus) | 不变 | 保留 |
| PluginStorage | 不变 | 保留 |

### 2.2 移除项

| 原 V2 草案概念 | 处置 |
|---------------|------|
| `json:plugin_script` 协议 | 移除。脚本执行由 `json:plugin_use` 的 capability implementation 内部调度 |
| Rule Matcher (规则引擎) | 移除。when_to_use / avoid_when 作为 LLM 提示词注入 |
| `POST /api/plugins/runtime/activate` | 移除 |
| `POST /api/plugins/runtime/plugin-use` | 移除。在 WebSocket 流内执行 |
| `POST /api/plugins/runtime/plugin-script` | 移除 |
| `GET /api/plugins/runtime/invocations/{id}` | 移除 |
| 4 文件强制要求（含 README.md / schemas/） | 改为 builtin 2 文件，external 4 文件 |

### 2.3 内置插件迁移与扩展要点

| 插件 | 类型 | 迁移要点 |
|------|------|---------|
| core-blocks | global/required | blocks（state_update / character_sheet / scene_update / event / notification）→ manifest.json.blocks；prompt(system, 95) → manifest.json.prompt；runtime_settings → manifest.json.extensions |
| database | global/required | prompt(world-state, 100) → manifest.json.prompt；storage keys → manifest.json.storage |
| character | gameplay/required | prompt(character, 10) → manifest.json.prompt；dep(database, core-blocks) → manifest.json.dependencies；storage keys → manifest.json.storage |
| memory | global/optional | prompt(memory, 10) → manifest.json.prompt；dep(database) → manifest.json.dependencies；storage keys → manifest.json.storage |
| archive | global/required | prompt(memory, 5) → manifest.json.prompt；dep(database) → manifest.json.dependencies；storage keys → manifest.json.storage |
| choices | gameplay/optional | blocks(choices) → manifest.json.blocks；prompt(pre-response, 80) → manifest.json.prompt；runtime_settings → manifest.json.extensions |
| auto-guide | gameplay/optional | blocks(guide) → manifest.json.blocks；prompt(pre-response, 90) → manifest.json.prompt；runtime_settings → manifest.json.extensions |
| dice-roll | gameplay/optional | blocks(dice_result) → manifest.json.blocks；events(dice-rolled) → manifest.json.events；prompt(pre-response, 70) → manifest.json.prompt。V2 可选增加 capability `dice.roll`（implementation: script） |
| story-image | gameplay/optional | blocks(story_image) → manifest.json.blocks；prompt(pre-response, 92) → manifest.json.prompt；dep(core-blocks, database) → manifest.json.dependencies；runtime_settings → manifest.json.extensions |
| skill-check | gameplay/optional | V2 新增插件：blocks(skill_check / skill_check_result) + capability `skill_check.resolve`（script） |
| combat | gameplay/optional | V2 新增插件：blocks(combat_start / combat_action / combat_round / combat_end) + capability `combat.resolve_action` |
| inventory | gameplay/optional | V2 新增插件：blocks(item_update / loot) + capability `inventory.use_item` |
| quest | gameplay/optional | V2 新增插件：block(quest_update) + storage/event 声明式动作 |
| faction | gameplay/optional | V2 新增插件：block(reputation_change) |
| relationship | gameplay/optional | V2 新增插件：block(relationship_change) |
| status-effect | gameplay/optional | V2 新增插件：block(status_effect) + capability `status_effect.tick` |
| codex | gameplay/optional | V2 新增插件：block(codex_entry) |

---

## 3. 组件架构

### 3.1 保留组件（V1 不变）

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| PromptBuilder | `backend/app/core/prompt_builder.py` | 6 位置 prompt 组装 |
| block_parser | `backend/app/core/block_parser.py` | `extract_blocks()` / `strip_blocks()` |
| block_validation | `backend/app/core/block_validation.py` | builtin schema 校验 + 语义校验 |
| PluginEventBus | `backend/app/core/event_bus.py` | 请求级事件总线 |
| GameStateManager | `backend/app/core/game_state.py` | DB 操作（messages / characters / world） |
| PluginStorage | `backend/app/models/plugin_storage.py` | 插件键值存储 |

### 3.2 增强组件

| 组件 | 代码位置 | V2 变更 |
|------|---------|--------|
| PluginEngine | `backend/app/core/plugin_engine.py` | discover/load 支持 manifest.json；get_prompt_injections 从 manifest 读 prompt 配置；get_block_declarations 从 manifest 读 blocks |
| dispatch_block | `backend/app/core/block_handlers.py` | 新增 `plugin_use` block 类型分支 → 路由到 capability 执行 |
| validate_block_data | `backend/app/core/block_validation.py` | 支持从 schemas/ 目录加载外部 schema 文件 |
| chat_service | `backend/app/services/chat_service.py` | process_message 中处理 plugin_use block：执行 capability → 收集 result blocks → 注入后续流程 |
| plugins API | `backend/app/api/plugins.py` | GET /api/plugins 返回 manifest 级元数据；新增导入/审计端点 |

### 3.3 新增组件（已实现）

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| CapabilityExecutor | `backend/app/core/capability_executor.py` | 执行 plugin_use 请求：校验 capability 声明 → 分发到 implementation（builtin / script / template）→ 收集结果 |
| ScriptRunner | `backend/app/core/script_runner.py` | Python 脚本执行：stdin JSON → subprocess → stdout JSON + exit code → 审计记录 |
| ManifestLoader | `backend/app/core/manifest_loader.py` | 解析 manifest.json + schemas/ 目录，生成运行时 PluginManifest 对象 |
| AuditLogger | `backend/app/core/audit_logger.py` | 脚本执行审计日志记录（JSON-lines，按天轮转） |
| PluginExporter | `backend/app/core/plugin_export.py` | 插件导出存根（zip/tarball，待实现） |

---

## 4. 执行流程

### 4.1 Prompt 组装流（每轮 Turn 开始时）

与 V1 一致，V2 仅改变元数据来源：

```
chat_service.process_message()
  │
  ├─ PluginEngine.resolve_dependencies(enabled_names)   # 拓扑排序
  ├─ PluginEngine.get_prompt_injections(enabled_names, context)
  │     │
  │     ├─ 读 manifest.json.prompt → {position, priority, template}   # V2 新
  │     ├─ 渲染 Jinja2 模板（或 PLUGIN.md body）
  │     └─ 返回 [{position, priority, content}, ...]
  │
  ├─ PluginEngine.get_block_declarations(enabled_names)
  │     │
  │     ├─ 读 manifest.json.blocks → BlockDeclaration[]   # V2 新
  │     └─ 返回 {block_type → BlockDeclaration}
  │
  ├─ PromptBuilder.inject() × N                          # 6 位置不变
  │     位置 1: system     — world doc + global plugins
  │     位置 2: character  — character state + scene
  │     位置 3: world-state — game state + plugin state data
  │     位置 4: memory     — long/short-term memory + archive
  │     位置 5: chat-history — recent messages
  │     位置 6: pre-response — block instructions + capability list   # V2 增强
  │
  └─ PromptBuilder.build() → [{role, content}, ...]
```

**V2 对 pre-response 的增强**：除了 Direct Block 的 instruction 列表外，还注入已启用插件的 capability 列表和 `json:plugin_use` 调用格式说明。

### 4.2 Turn 处理流（LLM 响应后）

```
LLM streaming response
  │
  ├─ block_parser.extract_blocks(full_response)
  │     返回 [{type, data, raw}, ...]
  │
  ├─ 遍历 blocks:
  │     ├─ type == "plugin_use" ?
  │     │     ├─ 是 → CapabilityExecutor.execute(data, context)    # V2 新
  │     │     │         ├─ 校验 plugin/capability/args
  │     │     │         ├─ 查 manifest.capabilities[cap].implementation
  │     │     │         │     ├─ "builtin" → 调用注册的内置 handler
  │     │     │         │     ├─ "script"  → ScriptRunner.run(script_path, args)
  │     │     │         │     └─ "template" → 渲染 Jinja2 模板
  │     │     │         ├─ 收集 result_blocks + state_updates
  │     │     │         └─ 返回 result
  │     │     └─ result blocks 加入 processed_blocks
  │     │
  │     └─ 其他 type → dispatch_block() (V1 流程不变)
  │           ├─ builtin handler (state_update / character_sheet / ...)
  │           ├─ declarative handler (storage_write / emit_event / ...)
  │           └─ pass-through (转发前端)
  │
  ├─ event_bus.drain(context)
  ├─ 保存 assistant message
  └─ yield processed_blocks → WebSocket → 前端
```

### 4.3 V1 回退流（无 manifest.json 的插件）

```
PluginEngine.load(plugin_name)
  │
  ├─ manifest.json 存在？
  │     ├─ 是 → ManifestLoader 解析，返回 V2 PluginManifest
  │     └─ 否 → 回退 PLUGIN.md frontmatter 解析（V1 路径）
  │             └─ logger.warning("Plugin '{}' has no manifest.json, using V1 fallback")
  │
  └─ 后续流程统一（prompt injection / block declarations 接口不变）
```

---

## 5. Block 分类

### 5.1 Direct Output Blocks（LLM 直接输出）

LLM 在叙事文本中直接输出 `` ```json:<type> `` 格式。后端 `block_parser` 提取后走 `dispatch_block()` 既有路径。

| Block Type | 来源插件 | 后端 Handler | 前端 Renderer |
|-----------|---------|-------------|--------------|
| state_update | core-blocks | StateUpdateHandler (builtin) | 无（静默应用） |
| character_sheet | core-blocks | CharacterSheetHandler (builtin) | custom: character_sheet |
| scene_update | core-blocks | SceneUpdateHandler (builtin) | custom: scene_update |
| event | core-blocks | EventHandler (builtin) | 无（静默应用） |
| notification | core-blocks | 无（pass-through） | custom: notification |
| choices | choices | 无（pass-through） | custom: choices |
| guide | auto-guide | 无（pass-through） | custom: guide |
| dice_result | dice-roll | DeclarativeBlockHandler (storage_write + emit_event) | card (schema UI) |
| skill_check | skill-check | 无（触发后续 capability） | 无（静默应用） |
| skill_check_result | skill-check | DeclarativeBlockHandler (storage_write + emit_event) | custom: skill_check_result |
| combat_start | combat | DeclarativeBlockHandler (storage_write + emit_event) | custom: combat_start |
| combat_action | combat | 无（触发后续 capability） | 无（静默应用） |
| combat_round | combat | DeclarativeBlockHandler (storage_write) | custom: combat_round |
| combat_end | combat | DeclarativeBlockHandler (storage_write + emit_event) | custom: combat_end |
| item_update | inventory | DeclarativeBlockHandler (storage_write + emit_event) | card (schema UI) |
| loot | inventory | DeclarativeBlockHandler (storage_write + emit_event) | custom: loot |
| quest_update | quest | DeclarativeBlockHandler (storage_write + emit_event) | custom: quest_update |
| reputation_change | faction | DeclarativeBlockHandler (storage_write + emit_event) | custom: reputation_change |
| relationship_change | relationship | DeclarativeBlockHandler (storage_write + emit_event) | custom: relationship_change |
| status_effect | status-effect | DeclarativeBlockHandler (storage_write + emit_event) | custom: status_effect |
| codex_entry | codex | DeclarativeBlockHandler (storage_write + emit_event) | custom: codex_entry |
| story_image | story-image | StoryImageHandler (builtin) | custom: story_image |

### 5.2 Capability Invocation Blocks（`json:plugin_use`）

LLM 输出 `json:plugin_use`，后端执行 capability 后产出 result blocks。

```json
{
  "plugin": "dice-roll",
  "capability": "dice.roll",
  "args": { "expr": "2d6+3" }
}
```

**执行流程**：
1. `dispatch_block()` 识别 type == "plugin_use"
2. 交给 `CapabilityExecutor`
3. 查 `manifest.json.capabilities["dice.roll"].implementation`
4. implementation.type == "script" → `ScriptRunner.run("scripts/roll.py", args)`
5. 脚本 stdout JSON 解析为 result
6. result 封装为 result blocks（如 `dice_result`）返回

**与 Direct Blocks 的关系**：
- Direct Blocks：LLM 已知输出格式，直接产出结构化数据
- Capability Blocks：LLM 只知道"调用什么能力"，由后端决定如何执行并产出结果
- 一个插件可以同时声明 Direct Blocks 和 Capabilities

---

## 6. 安全模型

### 6.1 脚本执行

| 策略 | 规则 |
|------|------|
| 确认策略 | 默认无需确认（开发效率优先） |
| 支持语言 | Phase 1 仅 Python |
| 超时 | 默认 5000ms，manifest 可声明覆盖 |
| 文件系统 | 仅允许访问插件目录 + `data/` 目录 |
| 审计 | 每次执行必须记录 invocation_id / plugin / script / args / exit_code / duration_ms / stdout / stderr |

### 6.2 网络策略

| 插件类型 | 默认网络策略 |
|---------|------------|
| global | 允许联网 |
| gameplay | 禁止联网 |

manifest.json 的 `permissions.network` 可显式覆盖默认值。

### 6.3 存储隔离

插件存储通过 `PluginStorage` 表的 `(project_id, plugin_name, key)` 三元组隔离，V2 不变。

---

## 7. API 变更

### 7.1 增强现有端点

| 端点 | 变更 |
|------|------|
| `GET /api/plugins` | 返回新增字段：version / manifest_source / capabilities / schema_status |
| `POST /api/plugins/{name}/toggle` | 不变 |
| `GET /api/plugins/enabled/{project_id}` | 不变 |
| `GET /api/plugins/block-schemas?project_id=...` | schema 来源改为 manifest.json.blocks + schemas/ 文件 |
| `GET /api/plugins/block-conflicts?project_id=...` | 不变 |

### 7.2 新增端点

| 端点 | 用途 |
|------|------|
| `POST /api/plugins/import/validate` | 校验待导入插件包（manifest + PLUGIN.md + schemas 一致性） |
| `POST /api/plugins/import/install` | 安装外部插件到 user library |
| `GET /api/plugins/{name}/audit` | 查询插件脚本执行审计日志 |

### 7.3 移除端点（原 V2 草案中的 runtime 端点）

以下端点**不再实现**，plugin_use 在 WebSocket 聊天流中执行：

- ~~POST /api/plugins/runtime/activate~~
- ~~POST /api/plugins/runtime/plugin-use~~
- ~~POST /api/plugins/runtime/plugin-script~~
- ~~GET /api/plugins/runtime/invocations/{id}~~

---

## 8. 前端影响

### 8.1 无变化

- WebSocket 事件协议不变：`chunk` / `done` / `state_update` / `error` / 自定义 block type
- Block renderer 注册系统不变：`registerBlockRenderer(type, Component)`
- 当前 custom renderers 包括：`choices` / `guide` / `notification` / `character_sheet` / `scene_update` / `story_image` / `skill_check_result` / `combat_start` / `combat_round` / `combat_end` / `loot` / `quest_update` / `reputation_change` / `relationship_change` / `status_effect` / `codex_entry`
- sessionStore 的 pendingBlocks 机制不变

### 8.2 需更新

| 变更 | 说明 |
|------|------|
| `Plugin` 类型定义 | 新增 version / manifest_source / capabilities / schema_status 字段 |
| PluginPanel 组件 | 展示 manifest 级元数据（version / capabilities / schema_status） |
| pluginStore | 消费 GET /api/plugins 新增字段 |
| plugin_use result blocks | 新 block type 需注册对应 renderer（或使用 generic JSON fallback） |

---

## 9. 实施状态

> 以下四个阶段均已完成实现。

### Phase A：manifest.json 基础 + V1 回退 ✅

1. ManifestLoader 实现（解析 manifest.json + schemas/ 目录）
2. PluginEngine 增强：优先读 manifest，无 manifest 回退 V1
3. 17 个内置插件全部完成 manifest.json 迁移
4. PLUGIN.md frontmatter 精简为 LLM 专有字段
5. `GET /api/plugins` 返回 manifest 级元数据（含 i18n、default_enabled、supersedes）

### Phase B：plugin_use 调用协议 ✅

1. CapabilityExecutor + ScriptRunner + AuditLogger 全部实现
2. dispatch_block 支持 plugin_use 分支
3. pre-response 指令注入 capability 列表和 plugin_use 格式说明
4. 已实现 capability：`dice.roll` / `skill_check.resolve` / `combat.resolve_action` / `inventory.use_item` / `status_effect.tick`

### Phase C：导入与审计 ✅

1. `POST /api/plugins/import/validate` 和 `POST /api/plugins/import/install` 端点实现
2. schemas/ 索引优先 / 扫描回退加载
3. `GET /api/plugins/{name}/audit` 审计日志查询端点实现
4. 前端 PluginPanel 展示 manifest 元数据（含详情弹窗、i18n 名称）

### Phase D：生态扩展（部分）

- [x] 运行时设置（runtime_settings）：按插件配置 + project/session 范围 + 多语言标签
- [x] 插件 i18n（名称、描述、设置项标签、枚举选项）
- [x] `supersedes` 字段（auto-guide 替代 choices）
- [x] `default_enabled` 字段
- [ ] 插件导出（zip/tarball）— 存根已存在，待实现
- [ ] 多语言脚本支持（JavaScript）
- [ ] 项目级模板覆盖
- [ ] 插件市场基础设施

---

## 10. 代码路径映射

### 10.1 后端 — 现有文件（需修改）

| 文件 | 修改内容 |
|------|---------|
| `backend/app/core/plugin_engine.py` | discover/load 支持 manifest.json；回退 V1 |
| `backend/app/core/block_handlers.py` | dispatch_block 新增 plugin_use 分支 |
| `backend/app/core/block_validation.py` | 支持外部 schema 文件加载 |
| `backend/app/services/chat_service.py` | process_message 处理 plugin_use block |
| `backend/app/api/plugins.py` | 新增导入/审计端点；增强 list 返回值 |
| `backend/app/services/plugin_service.py` | get_enabled_plugins 适配 manifest |

### 10.2 后端 — 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/core/manifest_loader.py` | manifest.json 解析 + schemas/ 加载 |
| `backend/app/core/capability_executor.py` | plugin_use 请求执行 |
| `backend/app/core/script_runner.py` | Python 脚本 subprocess 执行 |
| `backend/app/core/audit_logger.py` | 脚本执行审计 |

### 10.3 前端（需修改）

| 文件 | 修改内容 |
|------|---------|
| `frontend/src/types/index.ts` 或 `stores/pluginStore.ts` | Plugin 类型新增字段 |
| `frontend/src/services/api.ts` | 消费新增 API 字段 |
| `frontend/src/components/plugins/PluginPanel.tsx` | 展示 manifest 元数据 |

---

## 11. 假设与默认值

1. 首期脚本语言仅支持 Python。
2. 首期不做插件导出。
3. 首期不做项目级模板覆盖。
4. API 路径不加 `/v2`，直接增强现有语义。
5. 规范中的"推荐"在首版实现中按"必须"执行。
6. 无 manifest.json 的插件自动回退 V1 解析路径，日志输出弃用警告。

---

文档版本：v2.2
更新日期：2026-02-22
