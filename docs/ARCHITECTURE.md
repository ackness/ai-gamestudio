# AI GameStudio Architecture (Current Runtime)

> Describes the architecture implemented in code as of 2026-02-19.

---

## 1. System Topology

```text
Frontend (React + Zustand)
  - Chat UI (streaming, block renderers)
  - Side panels: characters / events / plugins / runtime settings
  - World editor (Markdown)
  - Storage: IndexedDB (offline) or backend API
            |
            | WebSocket (/ws/chat/{session_id})
            | HTTP fallback (/api/chat/{session_id}/command)
            | REST (/api/*)
            v
Backend (FastAPI + SQLModel + SQLite / PostgreSQL)
  - chat.py          — WebSocket & HTTP chat router
  - chat_service     — turn orchestration (async generator)
  - plugin_engine    — discovery / loading / manifest / dependency resolution
  - prompt_builder   — 6-position prompt assembly
  - block_parser     — json:xxx block extraction
  - block_handlers   — dispatch + built-in handlers
  - capability_executor — plugin_use capability invocation
  - script_runner    — Python subprocess execution
  - audit_logger     — append-only invocation audit trail
  - game_state       — DB operations (messages / characters / world)
            |
            v
LLM Gateway (litellm — supports 100+ providers)
```

---

## 2. Core Request Flow

### 2.1 Player Turn (message)

1. Frontend sends `{type:"message", content:"..."}` over WebSocket (or HTTP).
2. Backend stores the user message (`Message`).
3. Backend resolves enabled plugins for the project (topological sort).
4. Backend builds the prompt:
   - world doc system instruction
   - character / scene / event context (from manifest `prompt` configs)
   - plugin Jinja2 template injections
   - chat history
   - pre-response block instructions + capability list
5. Backend calls LLM in streaming mode; emits `chunk` events as tokens arrive.
6. After stream ends:
   - extract all `json:xxx` blocks from the full response
   - validate block data against plugin-declared schemas
   - dispatch each block: `plugin_use` → CapabilityExecutor; others → dispatch_block()
   - emit block events to frontend
7. Backend strips blocks from narration and stores assistant message.
8. Backend increments `turn_count`; optionally triggers archive summary.

### 2.2 WebSocket event ordering

For one turn the backend sends (all carry `turn_id`):

1. `chunk` (0…n)
2. `done`
3. Parsed block events (`scene_update`, `choices`, `story_image`, `guide`, etc.)
4. `turn_end`

Frontend attaches pending blocks to the matching assistant message via `turn_id + turn_end`.

### 2.3 HTTP chat fallback

`POST /api/chat/{session_id}/command` runs the same `process_message` pipeline and returns all events as a JSON array. Used on Vercel (no persistent WebSocket).

---

## 3. Plugin Runtime Model

The plugin system is **manifest-driven + declarative**. Every built-in plugin has both a `PLUGIN.md` (LLM-readable content) and a `manifest.json` (machine-readable metadata).

### 3.1 What is implemented

- Discover / load / validate plugins from `plugins/*/manifest.json` (V2) with automatic fallback to `PLUGIN.md` frontmatter (V1)
- Topological dependency ordering via Kahn's algorithm
- Jinja2 prompt template injection at 6 fixed positions
- File-signature-based process-local cache with hot reload
- Block declarations from `manifest.json.blocks` (with optional external schema files)
- Declarative block handler actions
- Request-scoped in-memory event bus
- Plugin storage via `PluginStorage` table `(project_id, plugin_name, key)`
- `json:plugin_use` capability invocation via `CapabilityExecutor`
- Python script execution via `ScriptRunner` (stdin/stdout JSON, configurable timeout)
- Append-only audit log (`data/audit/audit_YYYY-MM-DD.jsonl`)
- Plugin import/validate/install API
- Per-plugin audit log query API
- Frontend block UI via custom renderer registration or schema-driven generic renderer
- Plugin i18n (name / description / runtime settings labels per language)
- Runtime settings per plugin (scope: project or session)

### 3.2 Reserved (declared, not yet engine-executed)

- `hooks` lifecycle scripts (`on-load` / `on-turn-end`)
- Plugin-level `llm` task executor (independent scheduling / concurrency)
- `exports.commands/queries` unified call bus
- Plugin export to zip/tarball (stub exists in `plugin_export.py`)

---

## 4. Plugin Enablement and Dependency Semantics

### 4.1 Enablement sources (priority order)

1. `required: true` in `manifest.json` — always enabled
2. `world_doc` frontmatter `plugins: [...]` — project defaults
3. Explicit toggle records in `PluginStorage` (`key="_enabled"`)
4. `default_enabled: true` in `manifest.json` — opt-in default

### 4.2 `supersedes` field

A plugin can declare `supersedes: ["choices"]` in `manifest.json`. When enabled, the superseded plugin's prompt injections and block declarations are excluded even if it is also enabled. Used by `auto-guide` to replace `choices`.

### 4.3 Dependency behavior

- Dependencies are topologically ordered.
- Dependencies are auto-enabled transitively when required by an enabled plugin.
- Missing dependency → validation failure at load time.
- Disabling a plugin is blocked if another enabled plugin depends on it.

---

## 5. Prompt Assembly

Prompt positions are fixed (1–4 merge into one system message; 5 becomes role messages; 6 is final system message):

| # | Position | Typical content |
|---|----------|----------------|
| 1 | `system` | World doc + global plugin instructions |
| 2 | `character` | Player / NPC state + scene context |
| 3 | `world-state` | Current game state + plugin storage data |
| 4 | `memory` | Long/short-term memory + archive summary |
| 5 | `chat-history` | Recent user / assistant messages |
| 6 | `pre-response` | Block format instructions + capability list |

Template context keys available to plugins:

`project`, `characters`, `player`, `npcs`, `current_scene`, `scene_npcs`, `active_events`, `world_state`, `memories`, `archive`, `runtime_settings`

---

## 6. Block Protocol

### 6.1 LLM output contract

````text
```json:<type>
{ ...json... }
```
````

Parser also accepts a looser `json:<type>` marker without fencing (for weaker model output).

### 6.2 Block categories

**Direct Output Blocks** — LLM outputs these directly; dispatched via `dispatch_block()`:

| Block type | Handler | Frontend |
|-----------|---------|----------|
| `state_update` | built-in (DB write) | silent |
| `character_sheet` | built-in (DB write) | custom renderer |
| `scene_update` | built-in (DB write) | custom renderer |
| `event` | built-in (DB write) | silent |
| `notification` | pass-through | custom renderer |
| `choices` | pass-through | custom renderer |
| `guide` | pass-through | custom renderer |
| `dice_result` | declarative (storage_write + emit_event) | schema-driven card |
| `story_image` | built-in (image gen + DB) | custom renderer |

**Capability Invocation Blocks** — LLM outputs `json:plugin_use`; backend executes and produces result blocks:

```json
{"plugin": "dice-roll", "capability": "dice.roll", "args": {"expr": "2d6+3"}}
```

### 6.3 Backend dispatch priority

1. `type == "plugin_use"` → `CapabilityExecutor`
2. Built-in handler registry (`state_update`, `character_sheet`, `scene_update`, `event`, `story_image`)
3. Declarative handler actions from `manifest.json`
4. Pass-through to frontend

### 6.4 Declarative actions supported

`builtin` · `storage_write` · `emit_event` · `update_character` · `create_event`

Unknown action types are logged and skipped (non-fatal).

### 6.5 Server-side validation

Block data is validated against plugin-declared schemas (`blocks.<type>.schema`) and built-in minimal constraints before dispatch. Invalid blocks are skipped from state writes and converted into a visible `notification` error block.

---

## 7. Capability Execution (plugin_use)

```
CapabilityExecutor.execute(data, context)
  ├─ Validate plugin name + capability ID against manifest.capabilities
  ├─ Resolve implementation type:
  │     "builtin"  → call registered Python function
  │     "script"   → ScriptRunner.run(script_path, args, timeout_ms)
  │     "template" → render Jinja2 template
  ├─ Collect result_blocks (wrapped in result_block_type)
  └─ AuditLogger.log(invocation_id, plugin, capability, exit_code, duration_ms, …)
```

Script execution passes args as JSON on stdin, expects JSON output on stdout. Default timeout: 5000 ms (overridable per capability in `manifest.json`).

Audit log location: `data/audit/audit_YYYY-MM-DD.jsonl` (append-only JSON-lines, rotated daily).

---

## 8. Event Bus Semantics

The event bus is request-scoped and in-memory:

- Blocks emit events via `emit_event` declarative action.
- Plugins register listeners via `events.listen`.
- Queue is drained after all blocks are processed; events emitted during drain are also processed (breadth-first).
- Safety guard: max iterations to prevent infinite loops.
- No cross-request persistence.

---

## 9. Frontend Runtime Model

### 9.1 State stores

| Store | Responsibility |
|-------|---------------|
| `sessionStore` | Active session, messages, streaming state, pending blocks |
| `gameStateStore` | Characters, world state, events |
| `projectStore` | Project list + active project |
| `pluginStore` | Plugin list, enabled flags, detail metadata |
| `uiStore` | Language toggle, storage persistence flag |

### 9.2 Storage layer

`StorageFactory` probes `/api/health` on startup and selects:

- **`ApiSettingsStorage`** — delegates to backend REST API (local / self-hosted)
- **`LocalSettingsStorage`** — persists to browser IndexedDB (Vercel / no backend)

IndexedDB schema (`localDb.ts`) stores: `projects`, `sessions`, `messages`, `characters`, `scenes`, `events`, `plugin_state`, `runtime_settings`.

### 9.3 Renderer resolution

Block renderer lookup priority:

1. Custom renderer registered via `registerBlockRenderer(type, Component)`
2. Schema-driven generic renderer
3. Fallback collapsible JSON viewer

For `requires_response: true` blocks: frontend sends `block_response` → backend stores as `system_event` message → triggers a continuation turn with the response.

---

## 10. Data Model Ownership

| Entity | Key fields |
|--------|-----------|
| `Project` | `id`, `name`, `world_doc`, `init_prompt`, LLM config (model + key ref + base) |
| `GameSession` | `id`, `project_id`, `status`, `phase`, `game_state_json`, `turn_count` |
| `Message` | `id`, `session_id`, `role`, `content`, `raw_content` (with blocks), `metadata_json` |
| `Character` | `id`, `session_id`, `name`, `role`, `attributes_json`, `inventory_json` |
| `Scene` | `id`, `session_id`, `name`, `is_current`, `metadata_json` |
| `SceneNPC` | `scene_id`, `character_id`, `role_in_scene` |
| `GameEvent` | `id`, `session_id`, `type`, `status`, lifecycle fields |
| `PluginStorage` | `(project_id, plugin_name, key)` → `value_json` |

Notes:
- `raw_content` preserves original LLM output including block fences.
- Plugin state is namespaced by the three-column key `(project_id, plugin_name, key)`.
- `game_state_json` on `GameSession` stores ephemeral world variables.

---

## 11. Archive Subsystem

Archive plugin is `required: true` and always active.

- Per-session archive initialization on first turn.
- Auto-summary every N turns (default: 8).
- Manual summary via API.
- Versioned snapshots; restore to any snapshot.
- Archive summary injected into prompt `memory` position.

Restore modes:
- **`fork`** (default): new session branch, restore state there.
- **`hard`**: clear current session state (messages / characters / scenes / events) and restore in place.

---

## 12. API Surface

### 12.1 REST endpoints (selected)

| Router | Endpoints |
|--------|-----------|
| `chat.py` | `POST /api/chat/{id}/command`, `WS /ws/chat/{id}`, `GET /api/sessions/{id}/story-images`, `WS /api/sessions/{id}/debug-log` |
| `projects.py` | `GET/POST /api/projects`, `GET/PUT/DELETE /api/projects/{id}` |
| `sessions.py` | `POST /api/projects/{id}/sessions`, `GET /api/projects/{id}/sessions`, `DELETE /api/sessions/{id}`, `GET /api/sessions/{id}/messages`, `GET /api/sessions/{id}/state` |
| `characters.py` | `GET /api/sessions/{id}/characters`, `PUT /api/characters/{id}` |
| `scenes.py` | `GET /api/sessions/{id}/scenes`, `GET /api/sessions/{id}/scenes/current`, `GET /api/scenes/{id}/npcs` |
| `plugins.py` | `GET /api/plugins`, `POST /api/plugins/{name}/toggle`, `GET /api/plugins/enabled/{project_id}`, `GET /api/plugins/block-schemas`, `GET /api/plugins/block-conflicts`, `POST /api/plugins/import/validate`, `POST /api/plugins/import/install`, `GET /api/plugins/{name}/audit`, `GET /api/plugins/{name}/detail` |
| `templates.py` | `GET /api/templates/worlds`, `GET /api/templates/worlds/{slug}`, `POST /api/templates/worlds/generate` |
| `runtime_settings.py` | `GET /api/runtime-settings/schema/{project_id}`, `GET /api/runtime-settings/{project_id}`, `PATCH /api/runtime-settings/{project_id}` |
| `main.py` | `GET /api/health`, `GET /api/llm/info`, `GET /api/llm/preset-models` |

### 12.2 WebSocket client message types

`message` · `init_game` · `form_submit` · `character_edit` · `scene_switch` · `confirm` · `block_response` · `force_trigger` · `generate_message_image`

### 12.3 WebSocket server event types

`chunk` · `done` · `turn_end` · `error` · block events (any `json:xxx` type) · `phase_change` · `_message_saved`

---

## 13. Deployment Modes

### Local development

```
Vite :5173  →  proxy /api/* /ws/*  →  FastAPI :8000
```

### Local production

```
FastAPI :8000
  /api/*  →  REST routes
  /ws/*   →  WebSocket
  /*      →  frontend/dist/ (StaticFiles)
```

### Vercel (serverless)

```
app.py → FastAPI as Serverless Function (max 60s per request)
frontend/dist/ → Vercel CDN (built via vercel.json buildCommand)
```

- WebSocket not supported on Vercel; HTTP chat transport used instead (`VITE_CHAT_TRANSPORT=http`).
- Database: external PostgreSQL recommended; falls back to SQLite in `/tmp` (ephemeral).
- `GET /api/health` returns `storage_persistent: false` when running on Vercel + SQLite.
- Frontend detects this and falls back to IndexedDB; shows ephemeral storage banner.

---

Document version: `v2.0`
Updated: `2026-02-19`
