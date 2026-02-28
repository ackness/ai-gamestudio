# AI GameStudio (English)

> Build worlds in Markdown, play via chat, run RPG mechanics through plugins.

## Core Features

- Dual-model architecture: narrative LLM + plugin agent
- Plugin Spec v1: `manifest.json + PLUGIN.md`, `schema_version=1.0`
- Unified tool contract: 6 tools (`emit`, `db_read`, `db_log_append`, `db_log_query`, `db_graph_add`, `execute_script`)
- Persistent state: characters, scenes, events, plugin storage
- Long-session support: memory, archive, auto-compression

## Built-in Plugins

`database, state, event, memory, guide, codex, image, combat, inventory, social`

## Quick Start

```bash
git clone https://github.com/ackness/ai-gamestudio
cd ai-gamestudio
mise trust && mise install
cp .env.example .env
mise run setup
mise run dev:backend
mise run dev:frontend
```

Open `http://localhost:5173`.

## Plugin Test Script

```bash
uv run python scripts/test_plugin_agent.py --list
uv run python scripts/test_plugin_agent.py --all --dry-run --api-key dummy --model test-model
```

## Docs

- [Main README](README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Plugin Spec v1](docs/PLUGIN-SPEC.md)
- [Plugin Ecosystem](docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md)
