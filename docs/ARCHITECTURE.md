# AI GameStudio Architecture (Current Runtime)

> This document describes the architecture that is actually implemented in code today.
> Date baseline: 2026-02-16.

---

## 1. System Topology

```text
Frontend (React + Zustand)
  - Chat UI
  - Block renderers (custom + schema-driven)
  - Side panels (characters/events/world/plugins)
            |
            | WebSocket (/ws/chat/{session_id})
            | REST (/api/*)
            v
Backend (FastAPI + SQLModel + SQLite)
  - chat.py websocket router
  - chat_service.process_message orchestration
  - plugin_engine / prompt_builder / block_parser / block_handlers
  - game_state manager + archive_service
            |
            v
LLM Gateway (litellm)
```

---

## 2. Core Request Flow

### 2.1 Player Turn (message)

1. Frontend sends `{type:"message", content:"..."}` to WebSocket.
2. Backend stores user message (`Message`).
3. Backend resolves enabled plugins for the project.
4. Backend builds prompt:
   - world doc system instruction
   - character/scene/event context
   - plugin template injections
   - chat history
   - pre-response block instructions
5. Backend calls LLM in streaming mode.
6. Backend emits `chunk` events as tokens arrive.
7. After stream ends:
   - parse `json:xxx` blocks from full response
   - validate block data schema/minimal constraints
   - dispatch each block to handler
   - emit block events
8. Backend strips blocks from narration and stores assistant message.
9. Backend increments `turn_count` and optionally triggers archive summary.

### 2.2 WebSocket event ordering (important)

For one turn, the backend sends (all events carry `turn_id`):

1. `chunk` (0..n)
2. `done`
3. parsed block events (e.g. `scene_update`, `choices`, `event`)
4. `turn_end`

Frontend relies on `turn_id + turn_end` and attaches pending blocks to the matching assistant message.

---

## 3. Plugin Runtime Model

The plugin system is **document-driven + declarative**.

### 3.1 What is implemented

- Discover/load/validate plugins from `plugins/*/PLUGIN.md`
- Dependency ordering
- Prompt template injection (Jinja2)
- Plugin metadata/template process-local cache (`plugin_registry`) with file-signature hot reload
- Block declarations (`blocks`)
- Declarative block actions
- Request-scoped event bus (`events.listen`)
- Plugin storage via `PluginStorage`
- Frontend block UI via:
  - custom renderer registration
  - schema-driven generic renderer

### 3.2 What is reserved (declared but not engine-executed as a framework)

- `hooks` script lifecycle execution
- `llm` plugin-task execution framework
- `exports.commands/queries` runtime invocation bus

These fields may exist in plugin docs for forward compatibility but are not currently orchestrated as a standalone plugin runtime.

---

## 4. Plugin Enablement and Dependency Semantics

### 4.1 Enablement sources

Effective enabled plugin set per project is computed from:

1. `required: true` plugins (always enabled)
2. `world_doc` frontmatter `plugins: [...]` defaults
3. explicit toggle records in `PluginStorage` (`key="_enabled"`)

### 4.2 Dependency behavior

- Dependencies are used for topological ordering.
- Dependencies are auto-enabled transitively when required by enabled plugins.
- If dependency metadata points to missing plugin, validation fails.
- Disabling a plugin is blocked if it is required by currently enabled plugins.

---

## 5. Prompt Assembly

Prompt positions are fixed:

1. `system`
2. `character`
3. `world-state`
4. `memory`
5. `chat-history`
6. `pre-response`

Build behavior:

- Positions 1-4 are merged into one system message.
- Position 5 becomes role messages (`user`/`assistant`/`system`) in order.
- Position 6 is appended as final system message before completion.

Current template context keys provided by backend:

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

---

## 6. Block Protocol and Processing

### 6.1 LLM output contract

Structured data should be emitted as fenced blocks:

````text
```json:<type>
{ ...json... }
```
````

Parser also supports a looser `json:<type>` marker fallback for weaker model output.

### 6.2 Backend dispatch order

For each parsed block:

1. Built-in block handler registry (highest priority)
2. Plugin-declared `handler.actions`
3. Pass-through unchanged

Built-in handlers currently cover:

- `state_update`
- `character_sheet`
- `scene_update`
- `event`

### 6.3 Declarative actions currently supported

- `builtin`
- `storage_write`
- `emit_event`
- `update_character`
- `create_event`

Unknown action types are logged and skipped (non-fatal).

### 6.4 Server-side block validation

- Before dispatch, block data is validated against:
  - plugin-declared schema (`blocks.<type>.schema`)
  - built-in minimal constraints (`state_update`, `character_sheet`, `scene_update`, `event`)
- Invalid blocks are skipped from state writes and converted into a player-visible error notification block.

---

## 7. Event Bus Semantics

The event bus is request-scoped and in-memory:

- blocks can emit events via `emit_event`
- plugins can register listeners via `events.listen`
- queue is drained after all blocks are processed
- events emitted during drain are also processed (breadth-first)
- safety guard: max iterations to avoid infinite loop

No cross-request persistence exists for event bus state.

---

## 8. Frontend Runtime Model

### 8.1 State stores

- `sessionStore`: active session, messages, streaming state, pending blocks
- `gameStateStore`: characters, world state, events
- `pluginStore`: plugin list + enabled flags
- `blockSchemaStore`: block schemas from backend
- `blockInteractionStore`: block-level interactive UI state keyed by `block_id`

### 8.2 Renderer resolution

Block renderer lookup priority:

1. explicit custom renderer
2. schema-driven generic renderer
3. fallback JSON viewer

For `requires_response=true` schema blocks:

- frontend sends `block_response` payload with `block_type`
- backend stores response as `system_event` message
- backend triggers a continuation turn with the response summary

---

## 9. Data Model Ownership

Main entities:

- `Project`
- `GameSession`
- `Message`
- `Character`
- `Scene`
- `SceneNPC`
- `GameEvent`
- `PluginStorage`

Ownership notes:

- Session runtime state is split between relational entities and `game_state_json`.
- Plugin private state is namespaced by `(project_id, plugin_name, key)`.
- Assistant `raw_content` keeps original block-containing LLM response.

---

## 10. Archive Subsystem (Implemented)

Archive plugin is required and active by default.

Implemented capabilities:

- per-session archive initialization
- periodic auto-summary (default every 8 turns)
- manual summary API
- restore to any archived snapshot
- archive summary injection into prompt memory section

Restore behavior:

- supports two modes:
  - `fork` (default): create a new session branch and restore there
  - `hard`: clear current runtime state (messages/characters/scenes/events) and restore in place
- appends a restore marker system message

---

## 11. API and Protocol Surfaces

### 11.1 REST (selected)

- `/api/plugins`
- `/api/plugins/enabled/{project_id}`
- `/api/plugins/block-schemas?project_id=...`
- `/api/projects/*`
- `/api/sessions/*`
- `/api/events/*`
- `/api/scenes/*`
- `/api/sessions/{session_id}/archives*`

### 11.2 WebSocket client message types

- `message`
- `init_game`
- `form_submit`
- `character_edit`
- `scene_switch`
- `confirm`
- `block_response`

### 11.3 WebSocket server message types

- `chunk`
- `done`
- `turn_end`
- `error`
- block events (`state_update`, `scene_update`, `choices`, `event`, etc.)
- `phase_change`

---

## 12. Current Constraints and Non-Goals

1. Plugin hooks/scripts are not executed by a generic plugin runner.
2. Plugin-level `llm` config is not a separate scheduler/executor.
3. `events.emit` is declarative metadata; actual emission comes from actions.
4. Plugin metadata hot-reload uses file signature checks and process-local cache only (no distributed invalidation).
5. Frontend block interaction persistence is in-memory store keyed by `block_id` (not persisted across full page reloads).

---

## 13. Extension Direction

Architecture is prepared to evolve by extending, not replacing:

1. Add new declarative `handler.actions` types.
2. Add stricter optional block schema validation pipeline.
3. Introduce opt-in hook runner (`hooks`) under feature flag.
4. Add plugin command/query bus mapped from `exports`.
5. Keep compatibility via additive fields and graceful downgrade.

---

## 14. 当前未实现保留位

下列能力在文档/插件字段中可声明，但当前运行时不作为通用框架执行：

1. `hooks` 生命周期脚本（如 `on-load` / `on-turn-end`）
2. 插件级 `llm` 任务执行器（独立调度/重试/并发控制）
3. `exports.commands/queries` 统一调用总线
4. 通用 Python/JS 脚本沙箱执行入口（仅保留目录与依赖）

---

Document version: `v1.0-current`  
Updated: `2026-02-16`
