# AI GameStudio — 技术栈与开发环境

---

## 1. 技术选型总览

| 层级 | 技术 | 状态 | 版本 | 说明 |
|------|------|------|------|------|
| **开发环境** | mise | Implemented | latest | 工具版本管理 + 任务运行器 |
| **包管理(Python)** | uv | Implemented | latest | 通过 mise 管理，替代 pip/poetry |
| **前端框架** | Vite + React | Implemented | React 19 | 本地优先不需要 SSR，Vite 更轻量 |
| **UI 组件** | Tailwind CSS + 自定义组件 | Implemented | — | 当前并未引入 shadcn/ui |
| **Markdown 编辑器** | 原生 textarea + `react-markdown` 预览 | Implemented | — | 当前编辑器采用轻量实现 |
| **脚本编辑器** | Monaco Editor | Planned | — | 进阶脚本编辑能力预留 |
| **状态管理** | Zustand | Implemented | — | 轻量，适合游戏状态管理 |
| **后端框架** | FastAPI | Implemented | ≥0.115 | 原生 async，自带 WebSocket |
| **ASGI 服务器** | uvicorn | Implemented | ≥0.34 | 配合 FastAPI |
| **LLM 接入** | litellm | Implemented | ≥1.60 | 统一接口，100+ 模型供应商 |
| **数据库** | SQLite + aiosqlite | Implemented | — | 本地优先零配置 |
| **ORM** | SQLModel | Implemented | ≥0.0.24 | Pydantic + SQLAlchemy 集成 |
| **定时任务** | APScheduler | Planned | ≥3.11 | 依赖已引入，通用调度器未落地 |
| **脚本沙箱(Python)** | RestrictedPython | Planned | ≥7.4 | 依赖已引入，通用沙箱执行器未落地 |
| **脚本沙箱(JS)** | Node.js subprocess | Planned | — | 沙箱目录已预留，执行框架未落地 |
| **模板引擎** | Jinja2 | Implemented | ≥3.1 | Prompt 模板变量替换 |
| **插件元数据解析** | python-frontmatter | Implemented | ≥1.1 | 解析 PLUGIN.md 的 YAML frontmatter |
| **实时通信** | WebSocket | Implemented | — | 游戏消息推送、LLM 流式输出 |
| **代码质量** | Ruff | Implemented | ≥0.9 | Python lint + format 一体化 |
| **测试** | pytest + pytest-asyncio | Implemented | — | 后端测试 |
| **测试（前端）** | Vitest | Implemented | — | 提供 `npm test` 与关键逻辑测试 |

### Implemented / Planned 概览

| Implemented | Planned |
|-------------|---------|
| Vite + React + Zustand + Tailwind | Monaco Editor（脚本编辑器） |
| FastAPI + SQLModel + SQLite + WebSocket | APScheduler 通用任务编排 |
| litellm + Jinja2 + python-frontmatter | Python/JS 通用脚本沙箱执行器 |
| pytest / pytest-asyncio / Vitest | — |

### 关键技术决策

**为什么 Vite 而不是 Next.js**

本项目是本地部署的单页应用，Next.js 的 SSR/ISR/路由约定等能力用不上，反而增加了和 Python 后端集成的复杂度。Vite + React 构建出纯静态文件，由 FastAPI 直接托管，架构更简单。前端通过 `vite build` 输出到 `frontend/dist/`，FastAPI 通过 `StaticFiles` 挂载。

**为什么 litellm 而不是直接调各家 SDK**

litellm 用统一的 `completion()` 接口封装了 100+ 模型供应商（OpenAI、Claude、Ollama、vLLM 等），切换模型只需改一个字符串。这对"接入大模型接口"这个核心需求来说，避免了为每家 SDK 写适配代码。

**为什么 SQLite 而不是 PostgreSQL**

本地优先场景下 SQLite 零配置、单文件、随项目走，用户不需要安装额外数据库。SQLModel 的模型定义后续切到 PostgreSQL 改动很小。

**脚本沙箱策略**

Python 脚本用 RestrictedPython 做 AST 级别权限控制（禁止文件/网络/系统调用）。JS 脚本通过 `subprocess` 调 Node.js 执行。两种脚本都通过 stdin/stdout 传递 JSON 格式的 Context/Result，和主进程解耦。

---

## 2. 开发环境配置

### 前置要求

- [mise](https://mise.jdx.dev/) — 开发工具版本管理与任务运行器

### 初始化

```bash
# 1. 克隆项目后，信任 mise 配置
mise trust

# 2. 安装所有工具（python, node, uv）
mise install

# 3. 初始化完整开发环境（后端 + 前端）
mise run setup
```

### mise 管理的工具

```toml
[tools]
python = "3.12"       # Python 运行时
node = "22"           # Node.js（前端构建 + JS 脚本沙箱）
uv = "latest"         # Python 包管理器
```

mise 会自动为项目目录激活正确的工具版本。Python 依赖通过 `uv` 管理，不使用 pip。

---

## 3. mise 任务一览

所有开发操作通过 `mise run <task>` 执行。

### 环境设置

| 任务 | 命令 | 说明 |
|------|------|------|
| `setup` | `mise run setup` | 初始化完整开发环境（后端 + 前端） |
| `setup:backend` | `mise run setup:backend` | 创建 venv + 安装 Python 依赖 |
| `setup:frontend` | `mise run setup:frontend` | 安装前端 npm 依赖 |

### 开发服务器

| 任务 | 命令 | 说明 |
|------|------|------|
| `dev` | `mise run dev` | 同时启动后端 + 前端开发服务器 |
| `dev:backend` | `mise run dev:backend` | 启动 FastAPI（localhost:8000，热重载） |
| `dev:frontend` | `mise run dev:frontend` | 启动 Vite（localhost:5173，HMR） |

### 构建与生产

| 任务 | 命令 | 说明 |
|------|------|------|
| `build` | `mise run build` | 构建前端生产版本到 `frontend/dist/` |
| `start` | `mise run start` | 构建前端 → 启动 FastAPI 托管静态文件 |

### 代码质量

| 任务 | 命令 | 说明 |
|------|------|------|
| `lint` | `mise run lint` | 运行所有 lint 检查 |
| `lint:backend` | `mise run lint:backend` | Ruff 检查 Python 代码 |
| `lint:frontend` | `mise run lint:frontend` | ESLint 检查前端代码 |
| `format` | `mise run format` | 格式化所有代码 |
| `format:backend` | `mise run format:backend` | Ruff 格式化 Python |
| `format:frontend` | `mise run format:frontend` | Prettier 格式化前端 |

### 测试

| 任务 | 命令 | 说明 |
|------|------|------|
| `test` | `mise run test` | 运行所有测试 |
| `test:backend` | `mise run test:backend` | pytest 运行后端测试 |
| `test:frontend` | `mise run test:frontend` | 运行前端测试 |

### 数据库

| 任务 | 命令 | 说明 |
|------|------|------|
| `db:init` | `mise run db:init` | 初始化 SQLite 数据库 |
| `db:reset` | `mise run db:reset` | 删除并重建数据库 |

### 插件

| 任务 | 命令 | 说明 |
|------|------|------|
| `plugin:validate` | `mise run plugin:validate` | 验证所有 PLUGIN.md 格式 |
| `plugin:list` | `mise run plugin:list` | 列出所有已安装插件 |

### 清理

| 任务 | 命令 | 说明 |
|------|------|------|
| `clean` | `mise run clean` | 清理构建产物和缓存 |

---

## 4. 项目目录结构

```
ai-gamestudio/
├── mise.toml                  # mise 工具版本 + 任务定义
├── .gitignore
│
├── frontend/                  # Vite + React 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── editor/        # 世界观 Markdown 编辑器
│   │   │   ├── game/          # 游戏运行界面（对话/交互）
│   │   │   ├── plugins/       # 插件配置面板
│   │   │   └── status/        # 游戏状态面板
│   │   ├── stores/            # Zustand 状态管理
│   │   ├── services/          # API + WebSocket 客户端
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                   # FastAPI 后端
│   ├── app/
│   │   ├── main.py            # 入口，托管前端静态文件
│   │   ├── api/               # REST + WebSocket 路由
│   │   ├── core/
│   │   │   ├── plugin_engine.py    # 插件加载/调度/生命周期
│   │   │   ├── plugin_registry.py  # 插件元数据缓存入口（单例）
│   │   │   ├── prompt_builder.py   # Prompt 组装器
│   │   │   ├── llm_gateway.py      # LLM 网关 (litellm)
│   │   │   ├── game_state.py       # 游戏状态管理
│   │   │   └── block_validation.py # 服务端 block schema 校验
│   │   ├── sandbox/           # 脚本沙箱 (Python/JS)
│   │   ├── models/            # SQLModel 数据模型
│   │   ├── services/          # 业务逻辑
│   │   └── db/                # 数据库初始化与迁移
│   ├── tests/                 # 后端测试
│   ├── pyproject.toml         # Python 依赖声明
│   └── uv.lock                # uv 锁文件
│
├── data/                      # 用户数据（本地存储，git 忽略部分）
│   ├── projects/              # 游戏项目
│   │   └── my-game/
│   │       ├── world.md       # 世界观文档
│   │       ├── plugins/       # 项目自定义插件
│   │       └── saves/         # 存档
│   └── db.sqlite              # SQLite 数据库
│
├── plugins/                   # 内置插件
│   ├── database/
│   │   └── PLUGIN.md
│   ├── character/
│   │   ├── PLUGIN.md
│   │   ├── prompts/
│   │   └── schemas/
│   ├── memory/
│   │   └── PLUGIN.md
│   └── ...
│
└── docs/                      # 项目文档
    ├── PRD.md                 # 产品需求文档
    ├── PLUGIN-SPEC.md         # 插件规范
    └── TECH-STACK.md          # 本文档
```

---

## 5. 运行架构

### 开发模式

```
┌──────────────┐        ┌──────────────┐
│ Vite Dev     │  proxy  │ FastAPI      │
│ :5173        │ ──────→ │ :8000        │
│ (HMR)        │  /api/* │ (hot reload) │
└──────────────┘        └──────────────┘
```

前端 Vite 开发服务器将 `/api/*` 和 `/ws/*` 请求代理到 FastAPI 后端。

### 生产模式

```
┌──────────────────────────────┐
│ FastAPI :8000                │
│                              │
│  /api/*    → REST 路由       │
│  /ws/*     → WebSocket       │
│  /*        → frontend/dist/  │  ← 静态文件托管
└──────────────────────────────┘
```

单进程运行，FastAPI 同时托管 API 和前端静态文件。用户访问 `http://localhost:8000` 即可使用。

---

*文档版本：v0.1 | 创建日期：2026-02-15*
