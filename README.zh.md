# AI GameStudio（中文说明）

> 用 Markdown 构建世界，用聊天推进剧情，用插件稳定承载 RPG 机制。

## 核心特性

- 双层架构：主 LLM 负责叙事，Plugin Agent 负责机制执行。
- 插件规范 v1：`manifest.json + PLUGIN.md`，`schema_version=1.0`。
- 统一工具契约：6 个内置工具（`emit`, `db_read`, `db_log_append`, `db_log_query`, `db_graph_add`, `execute_script`），无历史版本分支。
- 持久状态：角色/场景/事件/插件存储统一落库。
- 长会话支持：记忆、归档、自动压缩。

## 内置插件

`database, state, event, memory, guide, codex, image, combat, inventory, social`

## 快速开始

```bash
git clone https://github.com/ackness/ai-gamestudio
cd ai-gamestudio
mise trust && mise install
cp .env.example .env
mise run setup
mise run dev:backend
mise run dev:frontend
```

访问 `http://localhost:5173`。

## 插件测试

```bash
uv run python scripts/test_plugin_agent.py --list
uv run python scripts/test_plugin_agent.py --all --dry-run --api-key dummy --model test-model
```

## 文档入口

- [README 主文档](README.md)
- [架构文档](docs/ARCHITECTURE.md)
- [插件规范 v1](docs/PLUGIN-SPEC.md)
- [插件生态架构](docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md)
