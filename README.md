# AI GameStudio

[中文（当前）](README.md) | [English](README.en.md)

> 把世界观写成 Markdown，把剧情玩成一款“可持续更新”的文字 RPG。

![image.png](.assets/image.png)

## 为什么是 AI GameStudio

多数 AI RPG 项目只能“会讲故事”，但难以“稳定维护游戏状态”。

AI GameStudio 的核心不是单次回复，而是**持续可玩的回合系统**：

- 主 LLM 专注叙事质量
- Plugin Agent 负责机制执行（战斗、状态、任务、图鉴、图片等）
- 所有机制都走统一插件规范 v1（`manifest.json + PLUGIN.md`）

## 亮点

- 双模型编排：叙事与机制解耦，互不干扰。
- 插件系统 v1：单一 schema、单一工具契约、无多版本分叉。
- 强状态一致性：角色/场景/事件/插件存储持久化。
- 可视化 block 管线：LLM 输出结构化 block，前端实时渲染。
- 长会话可维护：memory 插件提供归档与压缩。
- 低门槛扩展：新增插件即扩展玩法，不改主流程。

## 内置插件（10 个）

| 插件 | 分组 | 类型 | 作用 |
|---|---|---|---|
| `database` | core | global / required | 持久状态上下文 |
| `state` | core | global / required | 角色、场景、通知、状态同步 |
| `event` | core | global / required | 事件与任务生命周期 |
| `memory` | core | global / default-enabled | 记忆、归档、自动压缩 |
| `guide` | narrative | gameplay / default-enabled | 行动建议与交互选项 |
| `codex` | narrative | gameplay | 图鉴百科条目追踪 |
| `image` | narrative | gameplay / default-enabled | 剧情图像生成 |
| `combat` | rpg-mechanics | gameplay | 战斗、骰子、技能检定 |
| `inventory` | rpg-mechanics | gameplay | 物品与装备系统 |
| `social` | rpg-mechanics | gameplay | 关系与声望系统 |

## 3 分钟快速启动

### 1) 准备环境

- [mise](https://mise.jdx.dev/)
- 一个可用的 LLM API Key（LiteLLM 兼容）

### 2) 安装与运行

```bash
git clone https://github.com/ackness/ai-gamestudio
cd ai-gamestudio

mise trust && mise install
cp .env.example .env

# 至少配置 LLM_MODEL / LLM_API_KEY
mise run setup

# 终端 1
mise run dev:backend

# 终端 2
mise run dev:frontend
```

打开 `http://localhost:5173`。

### 3) 最小 .env

```env
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-key
LLM_API_BASE=https://api.deepseek.com
```

## 插件规范 v1（当前唯一版本）

### 目录结构

```text
plugins/
  <group>/
    group.json
    <plugin>/
      manifest.json
      PLUGIN.md
      prompts/
      scripts/
      schemas/
```

### manifest 关键约束

- `schema_version` 固定为 `1.0`
- 必需字段：`name/version/type/required/description`
- 插件加载不走 fallback

### Plugin Agent 工具（固定 7 个）

1. `update_and_emit`
2. `emit_block`
3. `db_read`
4. `db_log_append`
5. `db_log_query`
6. `db_graph_add`
7. `execute_script`

## 测试与验证

### 插件结构校验

```bash
mise run plugin:validate
```

### 插件 Agent 测试脚本（你提到的脚本）

```bash
# 列出可测试插件
uv run python scripts/test_plugin_agent.py --list

# dry-run（不调用外部模型）
uv run python scripts/test_plugin_agent.py --all --dry-run --api-key dummy --model test-model

# 实测（需要真实 API Key）
uv run python scripts/test_plugin_agent.py --all -v
```

## 常用命令

```bash
mise run dev
mise run test:backend
mise run test:frontend
mise run lint
mise run plugin:list
mise run plugin:validate
mise run plugin:test:dry-run
```

## 项目结构

```text
backend/app/
  api/        # FastAPI 路由
  core/       # 插件引擎、block 管线、基础能力
  services/   # chat/plugin_agent/runtime 等业务编排
  models/     # SQLModel
frontend/src/
  components/ # 游戏与编辑器组件
  stores/     # Zustand 状态
  services/   # api/websocket/localDb
plugins/      # 内置分组插件
docs/         # 架构与规范文档
```

## 深入文档

- [架构总览](docs/ARCHITECTURE.md)
- [插件规范 v1](docs/PLUGIN-SPEC.md)
- [插件生态架构](docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md)
- [技术栈](docs/TECH-STACK.md)
- [世界文档规范](docs/WORLD-SPEC.md)

## 部署

- 本地：SQLite 默认可直接运行
- Docker：`docker compose up -d --build`
- Vercel：HTTP 模式 + IndexedDB 兜底

## 许可证

MIT
