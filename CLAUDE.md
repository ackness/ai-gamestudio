# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI GameStudio is an LLM-native low-code RPG game editor and runtime. Users create worlds via Markdown documents, extend mechanics via a plugin system (`manifest.json` + `PLUGIN.md` format), and play through a DM (Dungeon Master) chat interface powered by LLM streaming.

## Commands

All tasks are managed via `mise`. Python packages use `uv` (project mode with `pyproject.toml`), frontend uses `npm`.

```bash
mise run setup              # Install all dependencies (backend + frontend)
mise run dev                # Start both backend (port 8000) and frontend (port 5173)
mise run dev:backend        # FastAPI dev server only
mise run dev:frontend       # Vite dev server only

mise run test               # Run all tests
mise run test:backend       # uv run pytest backend/tests/ -v
mise run test:frontend      # cd frontend && npm test

mise run lint               # Lint all code
mise run lint:backend       # uv run ruff check backend/
mise run format:backend     # uv run ruff format backend/

mise run build              # Build frontend for production
mise run plugin:validate    # Validate all plugin manifest.json files
mise run db:reset           # Drop and recreate SQLite database
```

Run a single backend test file: `uv run pytest backend/tests/test_chat_service.py -v`
Run a single test by name: `uv run pytest backend/tests/test_chat_service.py -k "test_extracts_state_update" -v`

## Architecture

### Backend (FastAPI + SQLite / PostgreSQL)

```
backend/app/
├── api/           # FastAPI routers (projects, sessions, chat, plugins, templates,
│                  #   characters, scenes, events, archive, llm_profiles, runtime_settings)
├── core/          # Framework internals
│   ├── block_parser.py        # Extracts ```json:xxx``` blocks from LLM output
│   ├── block_handlers.py      # Dispatches blocks to built-in or declarative handlers
│   ├── block_validation.py    # Validates block data against plugin-declared schemas
│   ├── plugin_engine.py       # Plugin discovery, loading, validation, dependency resolution
│   ├── manifest_loader.py     # Parses manifest.json into PluginManifest dataclass
│   ├── capability_executor.py # Executes json:plugin_use capability calls
│   ├── script_runner.py       # Python subprocess execution (stdin/stdout JSON)
│   ├── audit_logger.py        # Append-only invocation audit log (data/audit/)
│   ├── plugin_export.py       # Plugin export stub (zip/tarball, not yet implemented)
│   ├── prompt_builder.py      # Assembles multi-section prompts for LLM calls
│   ├── llm_gateway.py         # LiteLLM wrapper (completion function)
│   ├── game_state.py          # GameStateManager — DB operations for messages, characters, world
│   └── event_bus.py           # Request-scoped in-memory event bus
├── models/        # SQLModel ORM (Project, GameSession, Message, Character, Scene,
│                  #   SceneNPC, GameEvent, PluginStorage)
├── services/      # Business logic
│   ├── chat_service.py              # process_message() — main turn orchestration
│   ├── plugin_service.py            # Plugin enablement state management
│   ├── runtime_settings_service.py  # Per-plugin runtime settings CRUD
│   ├── image_service.py             # Story image generation
│   └── archive_service.py           # Session archive and restore
└── db/            # Database engine and initialization
```

**Request flow for chat:** WebSocket at `/ws/chat/{session_id}` (or HTTP POST `/api/chat/{session_id}/command` for Vercel) → `chat.py` router → `chat_service.process_message()` (async generator yielding `chunk`/block/`error` events) → streamed back over WebSocket.

**PromptBuilder injection positions** (positions 1–4 merge into one system message, 5 becomes role-specific messages, 6 appends as final system message):
1. `system` — world doc, global plugins
2. `character` — character definitions
3. `world-state` — plugin state data
4. `memory` — long/short-term memory
5. `chat-history` — recent messages (parsed as `role: content`)
6. `pre-response` — block format instructions + capability list

### Frontend (React + Vite + Zustand)

```
frontend/src/
├── pages/         # ProjectListPage, ProjectEditorPage
├── components/    # game/ (GamePanel, ChatMessages, ChatInput, QuickActions),
│                  # editor/ (MarkdownEditor, CreateProjectWizard),
│                  # plugins/ (PluginPanel, PluginDetailPanel),
│                  # status/ (RuntimeSettingsPanel, game state panels)
├── stores/        # Zustand stores: sessionStore, gameStateStore, projectStore,
│                  #   pluginStore, uiStore
├── services/      # api.ts (REST), websocket.ts (GameWebSocket — WebSocket + HTTP fallback),
│                  # settingsStorage.ts (ISettingsStorage interface),
│                  # localDb.ts (IndexedDB wrapper for offline/Vercel mode)
└── blockRenderers.ts  # Central renderer registration (imported in main.tsx)
```

**WebSocket event types from backend:** `chunk` (streaming text), `done` (full response), `turn_end` (blocks attached here), `state_update` (game state change), `error`, and any `json:xxx` plugin block type (e.g. `choices`, `guide`, `story_image`).

**Block renderer system:** `registerBlockRenderer(type, Component)` in `services/blockRenderers.ts`. Registered renderers get `{data, onAction}` props. Unregistered block types fall back to collapsible JSON display. Registration happens in `src/blockRenderers.ts` (imported at startup).

**Storage layer:** `StorageFactory` probes `/api/health` on startup:
- `storage_persistent: true` → `ApiSettingsStorage` (delegates to backend REST)
- `storage_persistent: false` (Vercel + SQLite) → `LocalSettingsStorage` (IndexedDB via `localDb.ts`)

### Plugin System

Plugins live in `plugins/<name>/` with two files:
- `manifest.json` — machine-readable metadata (V2 format, required for new plugins)
- `PLUGIN.md` — LLM-readable content (always required)

Legacy plugins without `manifest.json` fall back to PLUGIN.md frontmatter (V1).

Key concepts:
- **Types:** `global` (always-on infrastructure) or `gameplay` (toggleable mechanics)
- **Dependencies:** declared in `manifest.json`, resolved via topological sort (Kahn's algorithm)
- **Prompt injection:** each plugin specifies `position` and `priority`; Jinja2 templates rendered with game context
- **json:xxx blocks:** plugins declare block types in `manifest.json.blocks`. The backend dispatches:
  - `plugin_use` → `CapabilityExecutor` (script/builtin/template)
  - `state_update` / `character_sheet` / `scene_update` / `event` → built-in DB handlers
  - others → forwarded to frontend block renderers
- **Capabilities:** plugins declare executable capabilities in `manifest.json.capabilities`; invoked via `json:plugin_use` blocks; scripts run via Python subprocess (stdin/stdout JSON), with audit logging
- **supersedes:** a plugin can declare `supersedes: ["choices"]` to replace another plugin's injections when enabled (used by `auto-guide`)
- **Runtime settings:** per-plugin configurable fields (label/description/options with i18n) stored in `PluginStorage`

Built-in plugins (9): `core-blocks`, `database`, `archive`, `memory`, `character`, `choices`, `auto-guide`, `dice-roll`, `story-image`

### World Templates

World templates live in `templates/worlds/*.md` with YAML frontmatter (name, description, genre, tags, language) + Markdown body. The body follows the structure defined in `docs/WORLD-SPEC.md`.

- **Backend:** `api/templates.py` provides `GET /api/templates/worlds` (list), `GET /api/templates/worlds/{slug}` (detail), and `POST /api/templates/worlds/generate` (AI generation using LLM + WORLD-SPEC as system prompt)
- **Frontend:** `CreateProjectWizard` component in `components/editor/` provides a multi-step project creation flow: blank start, template selection, or AI generation

### json:xxx Block Protocol

LLM responses can contain `` ```json:<type> `` fenced blocks. The framework:
1. **Backend** (`block_parser.py`): `extract_blocks()` parses all blocks; `strip_blocks()` removes them for storage
2. **Backend** (`block_handlers.py`): dispatches to built-in handlers, declarative manifest actions, or pass-through
3. **Backend** (`capability_executor.py`): handles `plugin_use` blocks — validates capability, executes script/builtin/template, logs to audit trail
4. **Backend** (`chat.py`): all block events collected and forwarded after `done` + `turn_end`
5. **Frontend** (`websocket.ts`): `state_update` → `onStateUpdate` callback; all others → `onBlock(type, data)` callback
6. **Frontend** (`sessionStore.ts`): non-state-update blocks go to `pendingBlocks` array
7. **Frontend** (`ChatMessages.tsx`): renders `pendingBlocks` using registered block renderers

## Configuration

Copy `.env.example` to `.env`. Default model is `deepseek/deepseek-chat` with `LLM_API_BASE=https://api.deepseek.com` — chosen for 1M context window, stable multi-turn tool calling, and best price/performance ratio. LLM calls go through LiteLLM so any supported provider works.

Key settings:
- `LLM_MODEL` (default: `deepseek/deepseek-chat`)
- `LLM_API_KEY` — required
- `LLM_API_BASE` (default: `https://api.deepseek.com`)
- `DATABASE_URL` (default: `sqlite+aiosqlite:///data/db.sqlite`; use `postgresql+asyncpg://...` for PostgreSQL)
- `IMAGE_GEN_MODEL` / `IMAGE_GEN_API_KEY` / `IMAGE_GEN_API_BASE` — optional story image generation

## Testing Conventions

- Backend tests use in-memory SQLite (`sqlite+aiosqlite://`) with `StaticPool`
- Async tests require `@pytest.mark.asyncio` decorator
- Shared fixtures in `backend/tests/conftest.py`: `db_engine`, `db_session`, `sample_project`, `sample_session`
- LLM calls are mocked in tests via `unittest.mock.patch`

## Docker

```bash
# Build and start (SQLite, default)
docker compose up -d --build

# With PostgreSQL
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build

# Custom port
PORT=9000 docker compose up -d
```

Startup banner prints access URLs:
- `http://localhost:{PORT}` — standard Docker
- `http://ai-gamestudio.orb.local` — OrbStack

Data persisted in Docker volume `ai-gamestudio-data`. PostgreSQL overlay uses `docker-compose.postgres.yml`.

## Deployment

- **Local:** `mise run dev` (dev) or `mise run start` (prod, serves `frontend/dist/` via FastAPI)
- **Docker:** `docker compose up -d --build` (SQLite default, PostgreSQL optional)
- **Vercel:** `app.py` + `vercel.json` included. HTTP chat transport (`VITE_CHAT_TRANSPORT=http`). No persistent DB on Vercel without `DATABASE_URL`; frontend falls back to IndexedDB and shows ephemeral storage banner. `GET /api/health` returns `storage_persistent` field for auto-detection.

## Toolchain: mise + uv

Python dependencies are managed via `uv` in project mode (`pyproject.toml` + `uv.lock`). `mise` handles tool version management and task orchestration. See the [official mise+uv integration docs](https://mise.jdx.dev/lang/python.html#mise-uv).

### How mise and uv work together

`mise.toml` declares tool versions:

```toml
[tools]
python = "3.12"
node   = "22"
uv     = "latest"

[settings]
python.uv_venv_auto = "source"   # auto-activates .venv created by uv
```

`python.uv_venv_auto = "source"` tells mise to automatically source the `.venv` that uv creates, so you never need to manually activate the virtualenv. Use `"create|source"` if you also want mise to create the venv when it doesn't exist.

After installing a new Python version via mise, sync it to uv:

```bash
mise sync python --uv   # writes mise's Python path to .python-version so uv uses it
```

### Common uv operations

```bash
uv sync                        # Install/update dependencies from pyproject.toml + uv.lock
uv add <package>               # Add a dependency (updates pyproject.toml + uv.lock)
uv add --group dev <package>   # Add a dev-only dependency
uv run <cmd>                   # Run a command inside the venv (ensures venv active + deps ready)
uv run pytest backend/tests/   # Example: run tests
```

`uv run` is the correct way to invoke project commands — it ensures the virtualenv is active and all dependencies are installed before execution. Mise tasks use `uv run` internally (e.g. `uv run pytest`, `uv run uvicorn`).

## Logging

The backend uses `loguru` instead of stdlib `logging`. Configuration is in `backend/app/core/logging.py`, initialized in the `main.py` lifespan.

- **Console:** colored format, DEBUG level
- **File:** `data/logs/app_{date}.log`, daily rotation, 30-day retention, gzip compressed
- **stdlib bridge:** `_InterceptHandler` forwards third-party library logs (uvicorn, sqlalchemy, etc.) to loguru
- **Usage:** `from loguru import logger` then `logger.info()` / `logger.error()` etc.

## Data Directory

`data/` is git-ignored entirely. Contents at runtime:
- `data/db.sqlite` — SQLite database
- `data/logs/` — application logs (loguru, daily rotation)
- `data/audit/` — plugin capability invocation audit trail (JSON-lines, daily rotation)
- `data/secrets/` — API key references (stored outside DB rows)
