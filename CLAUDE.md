# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Project Overview

AI GameStudio is an LLM-native RPG editor/runtime:
- Worldbuilding via Markdown docs
- Turn-based DM chat gameplay
- Plugin-driven mechanics via `manifest.json + PLUGIN.md`

Current architecture is a **two-stage turn pipeline**:
1. Narrative LLM generates pure narrative text.
2. Plugin Agent runs mechanics with tool-calling and emits structured outputs.

Plugin protocol is **single-version v1** (`schema_version: "1.0"`).

## Commands

Task runner: `mise`  
Python package/runtime: `uv`  
Frontend package manager: `npm`

```bash
mise run setup
mise run dev
mise run dev:backend
mise run dev:frontend

mise run test
mise run test:backend
mise run test:frontend

mise run lint
mise run lint:backend
mise run lint:frontend
mise run format:backend

mise run build
mise run start

mise run plugin:list
mise run plugin:validate
mise run plugin:test:list
mise run plugin:test:dry-run
mise run plugin:test -- --all -v

mise run db:init
mise run db:reset
```

Useful direct commands:

```bash
uv run pytest backend/tests/test_chat_service.py -v
uv run pytest backend/tests/test_chat_service.py -k "test_name" -v
cd frontend && npm test
uv run python scripts/test_plugin_agent.py --all -v
```

## Backend Architecture (FastAPI + SQLModel)

### Key modules

- `backend/app/services/chat_service.py`
  - Main turn orchestration (`process_message`, `retrigger_plugins`)
  - Narrative stream -> plugin stage -> block dispatch -> persistence
- `backend/app/services/turn_context.py`
  - Aggregates session/project/characters/scenes/events/plugin enablement/runtime settings
- `backend/app/services/prompt_assembly.py`
  - Builds narrative-only prompt (explicitly no block instructions)
- `backend/app/services/plugin_agent.py`
  - Parallel per-plugin tool-calling (`MAX_TOOL_ROUNDS = 8`)
- `backend/app/core/plugin_engine.py`
  - Plugin discovery/loading/validation/dependency resolution/block declarations
- `backend/app/core/manifest_loader.py`
  - `manifest.json` schema validation + metadata normalization
- `backend/app/core/block_handlers.py`
  - Built-in + declarative block dispatch
- `backend/app/services/runtime_settings_service.py`
  - Runtime settings schema/value resolution and scope validation

### Chat request flow

WebSocket mode:
- `WS /ws/chat/{session_id}` -> `backend/app/api/chat.py` -> command router -> handlers -> `chat_service`

HTTP fallback mode (Vercel-compatible):
- `POST /api/chat/{session_id}/command` -> same command router and event protocol

Single-plugin invoke endpoint:
- `POST /chat/{session_id}/plugin/{plugin_name}`

### Turn execution (current behavior)

1. Build turn context (`build_turn_context`)
2. Build narrative prompt (`assemble_narrative_prompt`)
3. Stream narrative (`chunk`), then emit `done`
4. Persist assistant message + token usage (`token_usage`)
5. Enter plugin phase (`phase_change: plugins`)
6. Run Plugin Agent (`hook=post_model_output`)
7. Emit plugin progress (`plugin_progress`) and summary (`plugin_summary`)
8. Validate and dispatch emitted blocks
9. Persist message blocks in metadata
10. Emit `turn_end`

## Frontend Architecture (React + Zustand)

### Main modules

- `frontend/src/components/game/GamePanel.tsx` — primary play UI
- `frontend/src/hooks/useGameWebSocket.ts` — transport lifecycle + callback wiring
- `frontend/src/hooks/useWsCallbacks.ts` — event-to-store mapping
- `frontend/src/hooks/useGameActions.ts` — user command actions
- `frontend/src/services/websocket.ts` — WebSocket transport + HTTP fallback

### Transport and events

Default is WebSocket. If backend storage is non-persistent, frontend can fallback to HTTP command mode.

Primary backend event types consumed by frontend:
- `chunk`, `done`
- `phase_change`
- `state_update`, `scene_update`, `event`, `notification`
- `plugin_progress`, `plugin_summary`
- `message_blocks_updated`, `turn_end`
- `token_usage`
- `message_image_loading`, `message_image`
- `error`

### Block renderer system

- Registration: `frontend/src/blockRenderers.ts`
- Resolution: `frontend/src/services/blockRenderers.ts`
- Priority:
  1. Explicit custom renderer
  2. Schema-driven `GenericBlockRenderer`
  3. Fallback JSON renderer

## Plugin System (v1 only)

### Plugin layout

Supported layouts:

```text
plugins/<plugin>/
  manifest.json
  PLUGIN.md
```

```text
plugins/<group>/<plugin>/
  manifest.json
  PLUGIN.md
```

Grouped layout may include `plugins/<group>/group.json`.

Both files are required:
- `manifest.json` (machine contract)
- `PLUGIN.md` (LLM-facing behavior)

No multi-version fallback path is maintained.

### Manifest essentials

- `schema_version` must be `"1.0"`
- Required fields: `name`, `version`, `type`, `required`, `description`
- Outputs are declared in `manifest.outputs` (not legacy `blocks` terminology)

### Hook + trigger model

Canonical hooks:
- `pre_model_input`
- `post_model_output` (default)
- `frontend_action`
- `post_dispatch`

Backward-compatible aliases are normalized:
- `pre_narrative` -> `pre_model_input`
- `post_narrative` -> `post_model_output`
- `ui_action` -> `frontend_action`

Trigger modes:
- `always`
- `interval`
- `manual`

### Plugin Agent tool contract (fixed 6)

1. `emit`
2. `db_read`
3. `db_log_append`
4. `db_log_query`
5. `db_graph_add`
6. `execute_script`

`emit` is the unified structured output tool:
- `writes`: KV writes
- `logs`: append logs
- `items`: output envelopes (`type`, `data`, optional `id/meta/status`)

Only output types declared in `manifest.outputs` are accepted.

### Built-in plugins (current repo)

- core: `database` (required), `state` (required), `event` (required), `memory` (default-enabled)
- narrative: `guide` (default-enabled), `codex`, `image` (default-enabled)
- rpg-mechanics: `combat`, `inventory`, `social`

## Data Model and State

SQLModel entities include:
- `Project`, `GameSession`, `Message`
- `Character`, `Scene`, `SceneNPC`, `GameEvent`
- `PluginStorage`, `GameKV`, `GameLog`, `GameGraph`, archive-related models

Key notes:
- Plugin-scoped storage is namespaced by `(project_id, plugin_name, key)`
- Runtime settings store uses plugin namespace `runtime-settings`
- Compression summary currently persists under legacy keys:
  - plugin: `auto-compress`
  - keys: `compression-summary`, `compression-state`

## Legacy Compatibility Notes

Main gameplay path no longer depends on inline fenced `json:xxx` generation.
Narrative prompt explicitly forbids structured block output; mechanics come from Plugin Agent `emit` outputs.

Legacy JSON-block parsing still exists in limited compatibility paths (e.g., message history fallback parsing in session APIs).

## Configuration

Copy `.env.example` to `.env`.

Key environment variables:
- `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`
- Optional plugin model override: `PLUGIN_LLM_MODEL`, `PLUGIN_LLM_API_KEY`, `PLUGIN_LLM_API_BASE`
- Optional image generation: `IMAGE_GEN_MODEL`, `IMAGE_GEN_API_KEY`, `IMAGE_GEN_API_BASE`
- `DATABASE_URL` (SQLite default; PostgreSQL recommended for production)
- `PLUGINS_DIR`
- `ACCESS_KEY` (optional API protection)

## Testing Conventions

- Backend tests: `pytest` + async fixtures (`backend/tests/conftest.py`)
- Frontend tests: Vitest (`frontend/tests/`)
- Prefer mocking external LLM/image calls in tests
- Validate plugin changes with:
  - `mise run plugin:validate`
  - `mise run plugin:test:dry-run`

## Deployment Notes

- Local dev: `mise run dev`
- Docker: `docker compose up -d --build`
- Vercel: HTTP command transport + IndexedDB fallback for ephemeral backend storage

`GET /api/health` returns:
- `status`
- `storage_persistent`
- `auth_required`

## Logging and Data Paths

- Logging: `loguru` configured in `backend/app/core/logging.py`
- Runtime data (git-ignored):
  - `data/db.sqlite`
  - `data/logs/`
  - `data/audit/`
  - `data/secrets/`

## Related Docs

- `docs/ARCHITECTURE.md`
- `docs/PLUGIN-SPEC.md`
- `docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md`
- `docs/TECH-STACK.md`
- `docs/WORLD-SPEC.md`
