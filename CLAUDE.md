# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI GameStudio is an LLM-native low-code RPG game editor and runtime. Users create worlds via Markdown documents, extend mechanics via a plugin system (`PLUGIN.md` format), and play through a DM (Dungeon Master) chat interface powered by LLM streaming.

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
mise run plugin:validate    # Validate all PLUGIN.md files
mise run db:reset           # Drop and recreate SQLite database
```

Run a single backend test file: `uv run pytest backend/tests/test_chat_service.py -v`
Run a single test by name: `uv run pytest backend/tests/test_chat_service.py -k "test_extracts_state_update" -v`

## Architecture

### Backend (FastAPI + SQLite)

```
backend/app/
├── api/           # FastAPI routers (projects, sessions, chat, plugins, templates)
├── core/          # Framework internals
│   ├── block_parser.py    # Extracts ```json:xxx``` blocks from LLM output
│   ├── plugin_engine.py   # Plugin discovery, loading, validation, dependency resolution
│   ├── prompt_builder.py  # Assembles multi-section prompts for LLM calls
│   ├── llm_gateway.py     # LiteLLM wrapper (completion function)
│   └── game_state.py      # GameStateManager — DB operations for messages, characters, world
├── models/        # SQLModel ORM (Project, GameSession, Message, Character, PluginStorage)
├── services/      # Business logic (chat_service, plugin_service)
└── db/            # Database engine and initialization
```

**Request flow for chat:** WebSocket at `/ws/chat/{session_id}` → `chat.py` router → `chat_service.process_message()` (async generator yielding `chunk`/block/`error` events) → streamed back over WebSocket.

**PromptBuilder injection positions** (in order, positions 1–4 merge into one system message, 5 becomes role-specific messages, 6 appends as final system message):
1. `system` — world doc, global plugins
2. `character` — character definitions
3. `world-state` — plugin state data
4. `memory` — long/short-term memory
5. `chat-history` — recent messages (parsed as `role: content`)
6. `pre-response` — last-minute instructions

### Frontend (React + Vite + Zustand)

```
frontend/src/
├── pages/         # ProjectListPage, ProjectEditorPage
├── components/    # game/ (GamePanel, ChatMessages, ChatInput, ChoicesRenderer),
│                  # editor/ (MarkdownEditor, InitPromptEditor, CreateProjectWizard),
│                  # plugins/, status/
├── stores/        # Zustand stores: sessionStore, gameStateStore, projectStore, pluginStore
├── services/      # api.ts (REST), websocket.ts (GameWebSocket class), blockRenderers.ts
└── blockRenderers.ts  # Central renderer registration (imported in main.tsx)
```

**WebSocket event types from backend:** `chunk` (streaming text), `done` (full response), `state_update` (game state change), `error`, and any `json:xxx` plugin block type (e.g. `choices`).

**Block renderer system:** `registerBlockRenderer(type, Component)` in `services/blockRenderers.ts`. Registered renderers get `{data, onAction}` props. Unregistered block types fall back to collapsible JSON display. Registration happens in `src/blockRenderers.ts` (imported at startup).

### Plugin System

Plugins live in `plugins/<name>/PLUGIN.md` with YAML frontmatter + Markdown body. See `docs/PLUGIN-SPEC.md` for the full spec.

Key concepts:
- **Types:** `global` (always-on infrastructure) or `gameplay` (toggleable mechanics)
- **Dependencies:** declared in frontmatter, resolved via topological sort
- **Prompt injection:** each plugin specifies `position` and `priority`; Jinja2 templates in `prompts/` are rendered with game context
- **json:xxx blocks:** plugins define custom block types (e.g. `choices`). The backend `block_parser` extracts them generically; `state_update` blocks are applied to DB, all others are forwarded to the frontend.

### World Templates

World templates live in `templates/worlds/*.md` with YAML frontmatter (name, description, genre, tags, language) + Markdown body. The body follows the structure defined in `docs/WORLD-SPEC.md`.

- **Backend:** `api/templates.py` provides `GET /api/templates/worlds` (list), `GET /api/templates/worlds/{slug}` (detail), and `POST /api/templates/worlds/generate` (AI generation using LLM + WORLD-SPEC as system prompt)
- **Frontend:** `CreateProjectWizard` component in `components/editor/` provides a multi-step project creation flow with three options: blank start, template selection, or AI generation

### json:xxx Block Protocol

LLM responses can contain `` ```json:<type> `` fenced blocks. The framework:
1. **Backend** (`block_parser.py`): `extract_blocks()` parses all blocks; `strip_blocks()` removes them for storage
2. **Backend** (`chat_service.py`): `state_update` blocks are applied to DB; all block types are yielded as events
3. **Backend** (`chat.py`): all non-chunk/error events are collected and forwarded after the `done` message
4. **Frontend** (`websocket.ts`): `state_update` → `onStateUpdate` callback; all others → `onBlock(type, data)` callback
5. **Frontend** (`sessionStore.ts`): non-state-update blocks go to `pendingBlocks` array
6. **Frontend** (`ChatMessages.tsx`): renders `pendingBlocks` using registered block renderers

## Configuration

Copy `.env.example` to `.env`. Key settings: `LLM_MODEL` (default `gpt-4o-mini`), `LLM_API_KEY`, optional `LLM_API_BASE` for custom endpoints (e.g. Ollama). LLM calls go through LiteLLM so any supported provider works.

## Testing Conventions

- Backend tests use in-memory SQLite (`sqlite+aiosqlite://`) with `StaticPool`
- Async tests require `@pytest.mark.asyncio` decorator
- Shared fixtures in `backend/tests/conftest.py`: `db_engine`, `db_session`, `sample_project`, `sample_session`
- LLM calls are mocked in tests via `unittest.mock.patch`

## Toolchain: mise + uv

Backend Python 依赖通过 `uv` 项目模式管理（`pyproject.toml` + `uv.lock`），`mise` 负责编排工具版本和任务。

### mise.toml 关键配置

```toml
[tools]
python = "3.12"
uv = "latest"

[settings]
python.uv_venv_auto = true   # mise 自动激活 .venv

[tasks."setup:backend"]
run = "uv sync"               # 根据 pyproject.toml + uv.lock 安装依赖
```

### 常用操作

- 添加依赖: `uv add <package>` — 自动更新 `pyproject.toml` 和 `uv.lock`
- 添加开发依赖: `uv add --group dev <package>`
- 同步环境: `uv sync`
- 运行命令: `uv run <cmd>` — 自动确保虚拟环境激活并依赖就绪
- 版本同步: `mise sync python --uv` — 对齐 mise 安装的 Python 与 `.python-version`

### 参考

- mise + uv 集成文档: https://mise.jdx.dev/mise-cookbook/python.html#mise-uv

## Logging

后端使用 `loguru` 替代 stdlib `logging`。配置位于 `backend/app/core/logging.py`，在 `main.py` lifespan 中初始化。

- 控制台输出: 彩色格式，DEBUG 级别
- 文件日志: `data/logs/app_{date}.log`，每日轮转，保留 30 天，gzip 压缩
- stdlib 桥接: 通过 `_InterceptHandler` 将第三方库（uvicorn, sqlalchemy 等）的 stdlib logging 转发到 loguru
- 使用方式: `from loguru import logger`，直接调用 `logger.info()` / `logger.error()` 等
