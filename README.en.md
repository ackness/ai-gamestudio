# AI GameStudio

[中文](README.md) | [English (current)](README.en.md)

> Write your world in Markdown, advance the story through chat, and generate scene images at key moments.

![image.png](.assets/image.png)

---

## Core Concept

AI GameStudio is an **LLM-native low-code RPG engine**. You don't write any game logic — instead you:

1. Write a world document in Markdown (setting, characters, rules, factions…)
2. Advance the story through conversation — the DM (Dungeon Master) role is played by an LLM
3. Enable plugins on demand to add combat mechanics, memory archives, image generation, and more

---

## Features

### Narrative Engine
- Streaming WebSocket chat with real-time token-by-token output
- The main LLM focuses on pure narrative; a Plugin Agent appends structured blocks after each turn via tool calls
- Game state (characters, scenes, events) stored separately from narrative text, enabling continuous session play

### Plugin System
- Plugins are described by `plugins/<group>/<plugin>/manifest.json` plus `PLUGIN.md` in a grouped layout
- Topological dependency resolution with transitive auto-enable; `required` plugins cannot be disabled
- `supersedes` provides smooth replacement of legacy plugins, and `default_enabled` controls startup defaults
- Each plugin can inject prompt context, define custom block types, and declare capabilities (builtin or script)
- 10 built-in plugins included (4 Core + 3 Narrative + 3 RPG mechanics, see table below)

### World Editor
- Left-panel Markdown editor for live world document editing
- Create from templates with one click (cyberpunk, dark fantasy, urban xianxia, wuxia, epoch…)
- AI-assisted world document generation

### Novel Generation
- New `Novel` panel turns session materials (world doc/characters/events/messages) into chaptered prose
- Backend streams `outline` / `chapter_chunk` / `chapter` / `done` events
- Supports canceling generation mid-stream and exporting Markdown

### Story Images
- `image` plugin emits `story_image` blocks and triggers generation at key scenes automatically
- Continuity references (style consistency carried from the previous image)
- Regenerate any image from the frontend card with one click

### Save & Restore
- `memory` plugin unifies memory injection, archive snapshots, and auto-compression for long sessions
- Resume play from any saved snapshot

### Multilingual UI
- Chinese / English interface toggle (preference saved locally)
- Plugin settings — labels, descriptions, and enum options — all support i18n

### Flexible Storage
- Local run: full SQLite database, durable data
- Vercel deployment: automatic fallback to browser IndexedDB, per-user data, no database required
- Optional PostgreSQL via `DATABASE_URL` environment variable — no code changes needed

---

## Built-in Plugins

| Plugin | Group | Type | Description |
|--------|-------|------|-------------|
| `database` | core | Global (required) | Persistent state context for prompts; always enabled |
| `state` | core | Global (required) | State sync, character sheets, scene updates, notifications; supersedes `core-blocks` / `character` |
| `event` | core | Global (required) | Event and quest lifecycle tracking; supersedes `quest` |
| `memory` | core | Global (default-enabled) | Memory injection, archive snapshots, and auto-compression; supersedes `archive` / `auto-compress` |
| `guide` | narrative | Gameplay (default-enabled) | Action guidance and interactive choices; supersedes `auto-guide` / `choices` |
| `codex` | narrative | Gameplay | Codex/encyclopedia tracking |
| `image` | narrative | Gameplay (default-enabled) | Story image generation via `story_image`; supersedes `story-image` |
| `combat` | rpg-mechanics | Gameplay | Unified combat, dice rolls, skill checks, status effects; supersedes `dice-roll` / `skill-check` / `status-effect` |
| `inventory` | rpg-mechanics | Gameplay | Item updates, loot flow, and `inventory.use_item` capability |
| `social` | rpg-mechanics | Gameplay | NPC relationship and faction reputation tracking; supersedes `relationship` / `faction` |

---

## World Templates

| Template | Style |
|----------|-------|
| `cyberpunk` | Corporate dystopia, hackers, augmented humans |
| `dark-fantasy` | Corrupted gods, survival in a dying world |
| `urban-xianxia` | Modern city xianxia, spiritual revival, sect factions |
| `wuxia` | Martial arts, clan conflicts, inner power and honor |
| `epoch` | Historical narrative, social change, personal fate |

---

## Quick Start

### Prerequisites

- [mise](https://mise.jdx.dev/) (task runner + Python/Node version manager)
- An API key for any LiteLLM-compatible LLM provider (OpenAI, DeepSeek, OpenRouter, Ollama…)

### Install and Run

```bash
# Clone the repository
git clone https://github.com/ackness/ai-gamestudio
cd ai-gamestudio

# Install tool dependencies
mise trust && mise install

# Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum, set LLM_MODEL and LLM_API_KEY

# Install backend and frontend dependencies
mise run setup

# Start development servers
mise run dev:backend   # FastAPI on port 8000
mise run dev:frontend  # Vite on port 5173
```

Open `http://localhost:5173` to start building your world.

### Minimal .env

The default model is **DeepSeek V3.2** (`deepseek-chat`). Reasons:
- **1M context window**: entire world doc + full chat history fits in a single call, no truncation
- **Stable tool calling**: the `json:xxx` block protocol stays reliable across dozens of consecutive turns without degrading
- **Best price/performance ratio**: lowest cost among models of comparable quality; cheaper models can't match its block-call stability

```env
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-deepseek-key
LLM_API_BASE=https://api.deepseek.com
```

### Using OpenAI

```env
LLM_MODEL=gpt-5-mini-2025-08-07
LLM_API_KEY=your-openai-key
```

### Using Ollama (local model)

```env
LLM_MODEL=ollama/glm-4.7-flash
LLM_API_BASE=http://localhost:11434
```

### Enabling Story Image Generation

```env
IMAGE_GEN_MODEL=gemini-2.5-flash-image-preview
IMAGE_GEN_API_KEY=your-image-api-key
IMAGE_GEN_API_BASE=https://api.example.com/v1/chat/completions
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_MODEL` | Yes | `deepseek/deepseek-chat` | Model name in LiteLLM format |
| `LLM_API_KEY` | Yes | — | LLM provider API key |
| `LLM_API_BASE` | No | — | Custom API endpoint (Ollama / OpenRouter / self-hosted) |
| `IMAGE_GEN_MODEL` | No | — | Image generation model name |
| `IMAGE_GEN_API_KEY` | No | — | Image generation API key |
| `IMAGE_GEN_API_BASE` | No | — | Image generation API endpoint |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///data/db.sqlite` | Database connection string |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Allowed CORS origins (comma-separated) |
| `PLUGINS_DIR` | No | `plugins` | Plugin directory path |
| `SECRET_STORE_DIR` | No | `data/secrets` | API key reference storage directory |

---

## Deploy on Vercel

The repo includes `vercel.json` and `app.py` — import and deploy with no configuration required.

### Demo Mode (no database, works immediately)

Set these environment variables in your Vercel project:

```env
VITE_CHAT_TRANSPORT=http
VITE_API_BASE_URL=/api
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-api-key
```

- Data is stored in browser IndexedDB — each user's data is isolated, survives page refresh, and is lost only when browser storage is cleared
- The frontend shows a dismissible "ephemeral storage" notice

### Production Mode (with PostgreSQL)

```env
VITE_CHAT_TRANSPORT=http
VITE_API_BASE_URL=/api
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-api-key
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>/<db>
CORS_ORIGINS=https://your-domain.vercel.app
```

---

## Docker Deployment

The project ships with ready-to-use Docker support, built on `debian:12-slim` + mise in a multi-stage build — the frontend is compiled in Stage 1 and merged into the production image in Stage 2. **SQLite is the default database; no external database service is required.**

### Prerequisites

- Docker 20.10+ (or OrbStack)
- A `.env` file (copy from `.env.example`)

### Quick start

```bash
# 1. Configure environment variables
cp .env.example .env
# Edit .env — at minimum set LLM_API_KEY

# 2. Build and start
docker compose up -d --build
```

On startup the logs print the access URLs:

```
  AI GameStudio
  Local   →  http://localhost:8000
  OrbStack→  http://ai-gamestudio.orb.local
```

The SQLite database is stored in the Docker volume `ai-gamestudio-data` and survives container restarts and image rebuilds.

### File reference

| File | Description |
|------|-------------|
| `Dockerfile` | Multi-stage build: Stage 1 compiles frontend, Stage 2 runs backend |
| `docker-compose.yml` | Single-host deployment, SQLite database, persistent volume |
| `docker-compose.postgres.yml` | Optional overlay that adds a PostgreSQL service |

### Common operations

```bash
# Follow logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Custom port (default: 8000)
PORT=9000 docker compose up -d

# Backup the SQLite database
docker run --rm \
  -v ai-gamestudio-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/db-backup.tar.gz /data

# Open a shell inside the container
docker exec -it ai-gamestudio bash
```

### Switching to PostgreSQL (optional)

SQLite works well for personal use and small teams. For multi-instance or higher concurrency, apply the PostgreSQL overlay:

```bash
# Add to .env
POSTGRES_PASSWORD=your-strong-password

# Start with the postgres overlay
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

PostgreSQL data is persisted in a separate volume `ai-gamestudio-pg`. Recommended for self-hosted production deployments.

---

## Common Commands

```bash
mise run dev              # Start both backend and frontend
mise run dev:backend      # Backend only
mise run dev:frontend     # Frontend only
mise run setup            # Install all dependencies
mise run test             # Run all tests
mise run test:backend     # Backend tests only
mise run lint             # Lint all code
mise run format:backend   # Format backend code
mise run build            # Build frontend for production
mise run plugin:validate  # Validate all plugin manifests
mise run db:reset         # Drop and recreate the database
```

---

## Project Structure

```
├── backend/
│   └── app/
│       ├── api/           # FastAPI routers (chat, novel, projects, sessions, plugins, templates...)
│       ├── core/          # Framework internals (plugin_engine, plugin_tools, capability_executor, prompt_builder)
│       ├── services/      # Business logic (chat_service, plugin_agent, novel_service, plugin_service...)
│       └── models/        # SQLModel ORM models
├── frontend/
│   └── src/
│       ├── pages/         # ProjectListPage, ProjectEditorPage
│       ├── components/    # game/, editor/(incl. NovelPanel), plugins/, status/, ui/
│       ├── stores/        # Zustand stores (session, gameState, project, plugin, ui)
│       └── services/      # api.ts (incl. novel stream), websocket.ts, settingsStorage.ts, localDb.ts
├── plugins/               # Built-in grouped plugins (core / narrative / rpg-mechanics)
├── templates/worlds/      # World templates
└── docs/                  # Detailed documentation
```

---

## Further Reading

- [Plugin Spec](docs/PLUGIN-SPEC.md) — How to write custom plugins
- [Plugin Ecosystem Architecture](docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md) — Plugin system design
- [Architecture](docs/ARCHITECTURE.md) — System overview

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI · SQLModel · LiteLLM · SQLite / PostgreSQL |
| Frontend | React · Vite · Zustand · TypeScript · Tailwind CSS v4 · shadcn/ui (Radix) |
| Storage | SQLite (local) · PostgreSQL (production) · IndexedDB (browser offline) |
| AI | Any LiteLLM-compatible LLM · Separate image generation API |
| Toolchain | mise · uv · ruff |
