# AI GameStudio — 技术栈与开发环境

更新日期：2026-02-22

---

## 1. 技术选型总览

| 层级 | 技术 | 状态 | 说明 |
|------|------|------|------|
| **开发环境** | mise | ✅ 已实现 | 工具版本管理 + 任务运行器 |
| **包管理 (Python)** | uv | ✅ 已实现 | 替代 pip/poetry，通过 mise 管理 |
| **前端框架** | Vite + React 19 | ✅ 已实现 | 本地优先 SPA，Vite 更轻量 |
| **UI 样式** | Tailwind CSS v4 + shadcn/ui（Radix） | ✅ 已实现 | 统一主题 Token + 组件变体体系（CVA） |
| **Markdown 编辑器** | 原生 textarea + frontmatter 元数据面板 | ✅ 已实现 | 支持 AI 修订预览（search/replace）、流式生成与 `.md` 导出 |
| **状态管理** | Zustand | ✅ 已实现 | 轻量，适合游戏状态管理 |
| **浏览器存储** | IndexedDB (localDb.ts) | ✅ 已实现 | 离线 / Vercel 无数据库模式 |
| **后端框架** | FastAPI | ✅ 已实现 | 原生 async，自带 WebSocket |
| **ASGI 服务器** | uvicorn | ✅ 已实现 | 配合 FastAPI 热重载开发 |
| **LLM 接入** | LiteLLM | ✅ 已实现 | 统一接口，100+ 模型供应商 |
| **数据库** | SQLite + aiosqlite | ✅ 已实现 | 本地零配置，可切 PostgreSQL |
| **ORM** | SQLModel | ✅ 已实现 | Pydantic + SQLAlchemy 集成 |
| **模板引擎** | Jinja2 | ✅ 已实现 | Prompt 模板变量替换 |
| **插件元数据** | manifest.json + python-frontmatter | ✅ 已实现 | V2 manifest 优先，V1 frontmatter 回退 |
| **实时通信** | WebSocket + HTTP fallback | ✅ 已实现 | 游戏消息推送、LLM 流式输出；Vercel 用 HTTP |
| **小说生成流** | NDJSON Streaming | ✅ 已实现 | 按章节流式输出：outline/chapter_chunk/chapter/done |
| **连通性诊断** | `/api/llm/test` | ✅ 已实现 | 测试当前模型配置可用性并返回延迟 |
| **脚本执行** | Python subprocess | ✅ 已实现 | stdin/stdout JSON，带超时和审计日志 |
| **审计日志** | JSON-lines (append-only) | ✅ 已实现 | `data/audit/audit_YYYY-MM-DD.jsonl` |
| **代码质量** | Ruff | ✅ 已实现 | Python lint + format 一体化 |
| **测试** | pytest + pytest-asyncio | ✅ 已实现 | 后端测试，in-memory SQLite |
| **测试（前端）** | Vitest | ✅ 已实现 | 前端单元测试 |
| **脚本沙箱 (JS)** | Node.js subprocess | 🔜 规划中 | 目录已预留，执行框架未落地 |
| **定时任务** | APScheduler | 🔜 规划中 | 依赖已引入，通用调度器未落地 |
| **插件导出** | zip/tarball | 🔜 规划中 | plugin_export.py 存根已存在 |

### 关键技术决策

**为什么 Vite 而不是 Next.js**

本项目是本地部署的单页应用，Next.js 的 SSR/ISR/路由约定等能力用不上，反而增加与 Python 后端集成的复杂度。Vite + React 构建出纯静态文件，由 FastAPI 直接托管（生产模式）或 Vite 代理转发（开发模式）。

**为什么引入 shadcn/ui + Radix**

在大规模前端重构后，项目统一为 shadcn/ui 组件体系，底层使用 Radix primitives 保证可访问性，配合 Tailwind + CVA（`class-variance-authority`）统一变体风格，减少手写样式分叉并提升维护效率。

**为什么 LiteLLM 而不是直接调各家 SDK**

LiteLLM 用统一的 `completion()` 接口封装了 100+ 模型供应商（OpenAI、Claude、DeepSeek、Ollama、vLLM 等），切换模型只需改一个字符串，避免为每家 SDK 写适配代码。

**为什么 SQLite 而不是 PostgreSQL**

本地优先场景下 SQLite 零配置、单文件、随项目走，用户不需要安装额外数据库。SQLModel 的模型定义后续切到 PostgreSQL 只需修改 `DATABASE_URL`，零代码改动。

**为什么 IndexedDB 而不是 localStorage**

localStorage 有 5MB 上限，无法存储消息历史。IndexedDB 支持结构化查询（按 session_id 索引）、大容量存储，适合在 Vercel 等无持久数据库场景下作为前端完整存储层。

**脚本执行策略**

Python 插件脚本通过 `subprocess` 执行，args 以 JSON 传入 stdin，结果从 stdout 读取 JSON。每次执行记录审计日志（invocation_id / exit_code / duration_ms / stdout / stderr）。默认超时 5000ms，可在 `manifest.json` 中按 capability 覆盖。

---

## 2. 开发环境配置

### 前置要求

- [mise](https://mise.jdx.dev/) — 开发工具版本管理与任务运行器

### 初始化

```bash
# 克隆项目后，信任 mise 配置
mise trust

# 安装所有工具（python, node, uv）
mise install

# 初始化完整开发环境（后端 + 前端依赖）
mise run setup

# 复制并编辑环境变量
cp .env.example .env
# 至少填写 LLM_MODEL 和 LLM_API_KEY
```

### mise 管理的工具版本

```toml
[tools]
python = "3.12"
node   = "22"
uv     = "latest"
```

mise 自动为项目目录激活正确的工具版本。Python 依赖通过 `uv` 管理（`pyproject.toml` + `uv.lock`），不使用 pip。

---

## 3. mise 任务一览

### 环境设置

| 任务 | 说明 |
|------|------|
| `mise run setup` | 安装所有依赖（后端 + 前端） |
| `mise run setup:backend` | 仅安装 Python 依赖（`uv sync`） |
| `mise run setup:frontend` | 仅安装前端 npm 依赖 |

### 开发服务器

| 任务 | 说明 |
|------|------|
| `mise run dev` | 同时启动后端 + 前端开发服务器 |
| `mise run dev:backend` | FastAPI（localhost:8000，热重载） |
| `mise run dev:frontend` | Vite（localhost:5173，HMR） |

### 构建与生产

| 任务 | 说明 |
|------|------|
| `mise run build` | 构建前端生产版本到 `frontend/dist/` |
| `mise run start` | 构建前端 → 启动 FastAPI 托管静态文件 |

### 代码质量

| 任务 | 说明 |
|------|------|
| `mise run lint` | 运行所有 lint 检查 |
| `mise run lint:backend` | Ruff 检查 Python 代码 |
| `mise run lint:frontend` | ESLint 检查前端代码 |
| `mise run format:backend` | Ruff 格式化 Python |
| `mise run format:frontend` | Prettier 格式化前端 |

### 测试

| 任务 | 说明 |
|------|------|
| `mise run test` | 运行所有测试 |
| `mise run test:backend` | `uv run pytest backend/tests/ -v` |
| `mise run test:frontend` | 运行前端测试 |

### 数据库

| 任务 | 说明 |
|------|------|
| `mise run db:reset` | 删除并重建 SQLite 数据库 |

### 插件

| 任务 | 说明 |
|------|------|
| `mise run plugin:validate` | 验证所有插件 PLUGIN.md + manifest.json |
| `mise run plugin:list` | 列出所有已安装插件 |

---

## 4. 项目目录结构

```
ai-gamestudio/
├── mise.toml                    # mise 工具版本 + 任务定义
├── .env.example                 # 环境变量模板
├── app.py                       # Vercel 入口（from backend.app.main import app）
├── vercel.json                  # Vercel 部署配置
├── requirements.txt             # Vercel 用 pip 依赖列表
│
├── frontend/
│   └── src/
│       ├── pages/               # ProjectListPage, ProjectEditorPage
│       ├── components/
│       │   ├── editor/          # CreateProjectWizard, MarkdownEditor, NovelPanel
│       │   ├── game/            # ChatMessages, GamePanel, QuickActions
│       │   ├── plugins/         # PluginPanel, PluginDetailPanel
│       │   ├── status/          # RuntimeSettingsPanel, game state panels
│       │   └── ui/              # shadcn/ui primitives（button, dialog, tabs, ...）
│       ├── hooks/               # 自定义 React Hooks
│       │   ├── useGameWebSocket.ts  # WebSocket 生命周期 + 回调绑定 + 状态水合
│       │   ├── useGameActions.ts    # 游戏操作（发送/初始化/重试/触发等）
│       │   └── useArchive.ts        # 存档版本管理、保存/恢复
│       ├── stores/              # sessionStore, gameStateStore, projectStore, pluginStore, uiStore
│       ├── services/
│       │   ├── api.ts           # REST API client（含模板流式生成/修订）
│       │   ├── websocket.ts     # GameWebSocket (WebSocket + HTTP fallback)
│       │   ├── settingsStorage.ts  # ISettingsStorage 统一存储接口
│       │   ├── localDb.ts       # IndexedDB wrapper（离线模式）
│       │   └── idbSync.ts      # 统一 IDB 写入（缓存持久化状态）
│       ├── utils/
│       │   ├── browserLlmConfig.ts  # 浏览器本地 LLM/图片模型覆盖配置
│       │   ├── frontmatter.ts       # 世界文档 frontmatter 解析与序列化
│       │   └── sessionBootstrap.ts  # 会话启动辅助逻辑
│       ├── lib/
│       │   └── utils.ts         # shadcn className 工具（clsx + tailwind-merge）
│       ├── types/               # TypeScript 类型定义
│       └── blockRenderers.ts    # Block renderer 注册入口
│
├── backend/
│   └── app/
│       ├── main.py              # FastAPI 入口，静态文件托管，/api/health, /api/llm/test
│       ├── api/                 # FastAPI 路由
│       │   ├── chat.py          # WebSocket + HTTP chat（传输层）
│       │   ├── debug_log.py     # 调试日志环形缓冲 + story-images 端点
│       │   ├── novel.py         # 会话小说生成（NDJSON 流式输出）
│       │   ├── projects.py
│       │   ├── sessions.py
│       │   ├── characters.py
│       │   ├── scenes.py
│       │   ├── plugins.py
│       │   ├── templates.py     # 世界模板列表/详情、流式生成、search/replace 修订
│       │   ├── archive.py
│       │   ├── events.py
│       │   ├── llm_profiles.py
│       │   └── runtime_settings.py
│       ├── core/
│       │   ├── plugin_engine.py      # 插件发现 / 加载 / 验证 / 依赖排序
│       │   ├── manifest_loader.py    # manifest.json 解析
│       │   ├── capability_executor.py # plugin_use 能力执行
│       │   ├── script_runner.py      # Python 脚本 subprocess 执行
│       │   ├── audit_logger.py       # 审计日志（JSON-lines）
│       │   ├── plugin_export.py      # 插件导出（存根）
│       │   ├── prompt_builder.py     # 6 位置 Prompt 组装
│       │   ├── llm_gateway.py        # LiteLLM 封装
│       │   ├── block_parser.py       # json:xxx Block 提取
│       │   ├── block_handlers.py     # Block 分发 + 内置 Handler
│       │   ├── block_validation.py   # Block schema 校验
│       │   ├── search_replace.py     # search/replace edit block 解析与应用
│       │   ├── game_state.py         # GameStateManager DB 操作
│       │   └── event_bus.py          # 请求级事件总线
│       ├── services/
│       │   ├── chat_service.py       # process_message 回合编排
│       │   ├── turn_context.py       # TurnContext 数据类 + 异步加载
│       │   ├── prompt_assembly.py    # 纯函数 Prompt 组装
│       │   ├── block_processing.py   # Block 提取/校验/分发/事件排空
│       │   ├── command_handlers.py   # WebSocket 消息类型处理器
│       │   ├── plugin_service.py     # 插件启用状态管理
│       │   ├── runtime_settings_service.py  # 运行时设置 CRUD
│       │   ├── novel_service.py      # 小说素材收集、大纲与章节生成
│       │   ├── image_service.py      # 图片生成
│       │   └── archive_service.py    # 会话存档与恢复
│       ├── models/              # SQLModel ORM 模型
│       └── db/                  # 数据库初始化
│   └── tests/                   # pytest 测试
│
├── plugins/                     # 内置插件（每个含 PLUGIN.md + manifest.json）
│   ├── core-blocks/
│   ├── database/
│   ├── archive/
│   ├── memory/
│   ├── character/
│   ├── choices/
│   ├── auto-guide/
│   ├── dice-roll/
│   ├── skill-check/
│   ├── combat/
│   ├── inventory/
│   ├── quest/
│   ├── faction/
│   ├── relationship/
│   ├── status-effect/
│   ├── codex/
│   └── story-image/
│
├── templates/worlds/            # 世界观模板
│   ├── cyberpunk.md
│   ├── dark-fantasy.md
│   ├── urban-xianxia.md
│   ├── wuxia.md
│   └── epoch.md
│
├── data/                        # 运行时数据（git 忽略）
│   ├── db.sqlite
│   ├── logs/
│   └── audit/
│
└── docs/                        # 项目文档
    ├── ARCHITECTURE.md
    ├── PLUGIN-SPEC.md
    ├── PLUGIN-ECOSYSTEM-ARCHITECTURE.md
    ├── TECH-STACK.md
    ├── WORLD-SPEC.md
    └── PRD.md
```

---

## 5. 运行架构

### 开发模式

```
┌──────────────┐        ┌──────────────┐
│ Vite Dev     │  proxy  │ FastAPI      │
│ :5173        │ ──────→ │ :8000        │
│ (HMR)        │ /api/*  │ (hot reload) │
│              │ /ws/*   │              │
└──────────────┘        └──────────────┘
```

### 本地生产模式

```
┌──────────────────────────────┐
│ FastAPI :8000                │
│  /api/*   → REST 路由         │
│  /ws/*    → WebSocket         │
│  /*       → frontend/dist/   │
└──────────────────────────────┘
```

### Vercel（无服务器）

```
┌─────────────────────────────────┐
│ app.py → FastAPI Serverless Fn  │  (max 60s)
│  /api/* → REST 路由              │
│  （无 WebSocket，使用 HTTP chat） │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│ frontend/dist/ → Vercel CDN     │
└─────────────────────────────────┘
```

- Vercel 上 SQLite 存储在 `/tmp`（临时），推荐接入外部 PostgreSQL。
- 前端检测到 `storage_persistent: false` 时自动切换到 IndexedDB，并显示提示横幅。
