# AI GameStudio

[中文（当前）](README.md) | [English](README.en.md)

> 把世界观写成 Markdown，像聊天一样推进剧情，在关键时刻生成剧情画面。

![image.png](.assets/image.png)

---

## 核心理念

AI GameStudio 是一个**以 LLM 为驱动的低代码 RPG 引擎**。你不需要编写任何游戏逻辑——只需：

1. 用 Markdown 写好世界观文档（世界设定、角色、规则、门派……）
2. 通过对话推进剧情，DM（地下城主）由 LLM 扮演
3. 按需开启插件，扩展骰子、存档、图片生成等功能

---

## 功能特性

### 叙事引擎
- 流式 WebSocket 对话，实时逐字输出叙事内容
- 自动解析 LLM 输出中的结构化 `json:xxx` Block（选项、状态更新、事件……）
- 游戏状态（角色、场景、事件）与叙事内容分离存储，支持持续回合推进

### 插件系统
- 插件以 `plugins/<name>/manifest.json` + Markdown 文件描述，零代码扩展
- 支持插件依赖拓扑排序，避免冲突
- 每个插件可注入提示词、定义自定义 Block 类型、声明 `json:plugin_use` 能力
- 内置 17 款插件（4 全局 + 13 玩法，见下表）

### 世界观编辑器
- 左侧 Markdown 编辑器实时编辑世界文档
- 支持从模板一键创建（赛博朋克、黑暗奇幻、都市仙侠、武侠、年代……）
- 支持 AI 自动生成世界文档

### 小说生成
- 新增 `Novel` 面板：将会话素材（世界观/角色/事件/消息）编织为章节小说
- 后端按 `outline` / `chapter_chunk` / `chapter` / `done` 事件流式返回
- 支持随时中断生成，并一键导出 Markdown

### 剧情图片
- `story-image` 插件触发图片生成，关键场景自动出图
- 支持连续性参考（前一张图的风格延续）
- 前端图片卡片支持一键重生成

### 存档与恢复
- `archive` 插件：自动摘要长会话，支持版本化快照
- 可从任意存档点恢复继续游玩

### 多语言界面
- 中/英文界面切换（用户偏好保存到本地）
- 插件设置项的标签、描述、枚举选项均支持国际化

### 灵活存储
- 本地运行：SQLite 数据库，数据完整持久
- Vercel 部署：自动回退到浏览器 IndexedDB，数据保存在当前浏览器，无需数据库配置
- 可选接入 PostgreSQL，`DATABASE_URL` 直接切换，无需改代码

---

## 内置插件

| 插件 | 类型 | 功能 |
|------|------|------|
| `core-blocks` | 全局 | 状态同步、角色卡、场景、事件、通知等核心 Block 声明 |
| `database` | 全局 | 为提示词提供持久状态上下文，所有会话必须 |
| `archive` | 全局 | 长会话摘要与版本化快照存档 |
| `memory` | 全局 | 读取存储的记忆并注入到提示词 memory 位置 |
| `character` | 玩法 | 玩家/NPC 状态注入与角色相关输出引导 |
| `choices` | 玩法 | 交互式选项 Block（单选/多选） |
| `auto-guide` | 玩法 | AI 自动推荐行动选项（启用后替代 choices） |
| `dice-roll` | 玩法 | 骰子结果 Block + `dice.roll` 能力调用 |
| `skill-check` | 玩法 | 技能检定请求与结果 Block + `skill_check.resolve` |
| `combat` | 玩法 | 战斗开始/回合/结束 Block + `combat.resolve_action` |
| `inventory` | 玩法 | 物品变更与战利品 Block + `inventory.use_item` |
| `quest` | 玩法 | 任务创建/更新/完成/失败 Block |
| `faction` | 玩法 | 阵营声望变化 Block |
| `relationship` | 玩法 | NPC 关系变化 Block |
| `status-effect` | 玩法 | 状态效果 Block + `status_effect.tick` |
| `codex` | 玩法 | 图鉴/百科条目 Block |
| `story-image` | 玩法 | 结构化提示词生成剧情图片，支持连续性 |

---

## 世界观模板

| 模板 | 风格 |
|------|------|
| `cyberpunk` | 赛博朋克都市，企业统治，黑客与增强人 |
| `dark-fantasy` | 黑暗奇幻，腐化神明，求生于末日世界 |
| `urban-xianxia` | 都市仙侠，现代社会中的灵气复苏与宗门势力 |
| `wuxia` | 武侠江湖，门派纷争，内功与侠义 |
| `epoch` | 年代叙事，历史背景，社会变迁与个人命运 |

---

## 快速开始

### 前置条件

- [mise](https://mise.jdx.dev/)（任务运行器 + Python/Node 版本管理）
- 任意 LLM API Key（支持 OpenAI、DeepSeek、OpenRouter、Ollama 等 LiteLLM 兼容提供商）

### 安装与启动

```bash
# 克隆仓库
git clone https://github.com/ackness/ai-gamestudio
cd ai-gamestudio

# 安装工具依赖
mise trust && mise install

# 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，至少填写 LLM_MODEL 和 LLM_API_KEY

# 安装前后端依赖
mise run setup

# 启动开发服务器
mise run dev:backend   # FastAPI，端口 8000
mise run dev:frontend  # Vite，端口 5173
```

打开 `http://localhost:5173` 开始创建世界。

### 最小 .env 配置

默认使用 **DeepSeek V3.2**（`deepseek-chat`），推荐理由：
- **1M 超长上下文**：长篇世界观文档 + 完整对话历史一次性放入，不截断
- **工具调用稳定**：`json:xxx` Block 协议在几十轮连续对话中依然可靠触发，不退化
- **性价比最高**：同等能力里价格最低；更便宜的模型在 Block 稳定性上不如它

```env
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-deepseek-key
LLM_API_BASE=https://api.deepseek.com
```

### 使用 OpenAI

```env
LLM_MODEL=gpt-5-mini-2025-08-07
LLM_API_KEY=your-openai-key
```

### 使用 Ollama（本地模型）

```env
LLM_MODEL=ollama/glm-4.7-flash
LLM_API_BASE=http://localhost:11434
```

### 开启剧情图片生成

```env
IMAGE_GEN_MODEL=gemini-2.5-flash-image-preview
IMAGE_GEN_API_KEY=your-image-api-key
IMAGE_GEN_API_BASE=https://api.example.com/v1/chat/completions
```

---

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_MODEL` | 是 | `deepseek/deepseek-chat` | LiteLLM 格式模型名 |
| `LLM_API_KEY` | 是 | — | LLM 提供商 API Key |
| `LLM_API_BASE` | 否 | — | 自定义 API 端点（Ollama/OpenRouter/自托管） |
| `IMAGE_GEN_MODEL` | 否 | — | 图片生成模型名 |
| `IMAGE_GEN_API_KEY` | 否 | — | 图片生成 API Key |
| `IMAGE_GEN_API_BASE` | 否 | — | 图片生成 API 端点 |
| `DATABASE_URL` | 否 | `sqlite+aiosqlite:///data/db.sqlite` | 数据库连接字符串 |
| `CORS_ORIGINS` | 否 | `http://localhost:5173` | 允许的跨域来源（逗号分隔） |
| `PLUGINS_DIR` | 否 | `plugins` | 插件目录路径 |
| `SECRET_STORE_DIR` | 否 | `data/secrets` | API Key 引用存储目录 |

---

## 部署到 Vercel

本项目支持零配置 Vercel 部署（`vercel.json` 和 `app.py` 已内置）。

### 演示模式（无数据库，开箱即用）

在 Vercel 项目环境变量中配置：

```env
VITE_CHAT_TRANSPORT=http
VITE_API_BASE_URL=/api
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-api-key
```

- 数据存储在浏览器 IndexedDB，每个用户独立，刷新后保留，清除浏览器数据后丢失
- 前端会显示「临时存储」提示横幅

### 生产模式（接入 PostgreSQL）

```env
VITE_CHAT_TRANSPORT=http
VITE_API_BASE_URL=/api
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-api-key
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>/<db>
CORS_ORIGINS=https://your-domain.vercel.app
```

---

## Docker 部署

项目提供开箱即用的 Docker 支持，基于 `debian:12-slim` + mise 多阶段构建，前端编译后与后端合并为单一生产镜像。**默认使用 SQLite，无需额外数据库服务**。

### 前置条件

- Docker 20.10+（或 OrbStack）
- `.env` 文件（从 `.env.example` 复制）

### 快速启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填写 LLM_API_KEY

# 2. 构建镜像并启动
docker compose up -d --build
```

启动后日志会打印访问地址：

```
  AI GameStudio
  Local   →  http://localhost:8000
  OrbStack→  http://ai-gamestudio.orb.local
```

数据库文件存储在 Docker volume `ai-gamestudio-data` 中，容器重启或更新镜像后数据不丢失。

### 文件说明

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 多阶段构建：Stage 1 编译前端，Stage 2 生产后端 |
| `docker-compose.yml` | 单机部署，SQLite 数据库，数据持久化 volume |
| `docker-compose.postgres.yml` | 可选 overlay，追加 PostgreSQL 服务 |

### 常用操作

```bash
# 查看实时日志
docker compose logs -f

# 停止服务
docker compose down

# 更新代码后重新构建
docker compose up -d --build

# 自定义端口（默认 8000）
PORT=9000 docker compose up -d

# 备份 SQLite 数据库
docker run --rm \
  -v ai-gamestudio-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/db-backup.tar.gz /data

# 进入容器调试
docker exec -it ai-gamestudio bash
```

### 切换到 PostgreSQL（可选）

SQLite 适合个人使用和小团队。如需多实例或更高并发，可叠加 PostgreSQL overlay：

```bash
# .env 中增加
POSTGRES_PASSWORD=your-strong-password

# 启动时叠加 postgres overlay
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

PostgreSQL 数据持久化在独立 volume `ai-gamestudio-pg`，推荐在自托管生产环境使用。

---

## 常用命令

```bash
mise run dev              # 同时启动前后端
mise run dev:backend      # 仅启动后端
mise run dev:frontend     # 仅启动前端
mise run setup            # 安装所有依赖
mise run test             # 运行全部测试
mise run test:backend     # 仅运行后端测试
mise run lint             # 代码检查
mise run format:backend   # 后端代码格式化
mise run build            # 构建前端生产包
mise run plugin:validate  # 验证所有插件 manifest
mise run db:reset         # 重置数据库
```

---

## 项目结构

```
├── backend/
│   └── app/
│       ├── api/           # FastAPI 路由（chat, novel, projects, sessions, plugins, templates...）
│       ├── core/          # 框架内核（plugin_engine, capability_executor, prompt_builder, block_parser）
│       ├── services/      # 业务逻辑（chat_service, novel_service, plugin_service, archive_service...）
│       └── models/        # SQLModel ORM 模型
├── frontend/
│   └── src/
│       ├── pages/         # ProjectListPage, ProjectEditorPage
│       ├── components/    # game/, editor/(含 NovelPanel), plugins/, status/, ui/
│       ├── stores/        # Zustand 状态（session, gameState, project, plugin, ui）
│       └── services/      # api.ts（含小说流）、websocket.ts、settingsStorage.ts、localDb.ts
├── plugins/               # 内置插件
├── templates/worlds/      # 世界观模板
└── docs/                  # 详细文档
```

---

## 更多文档

- [插件规范](docs/PLUGIN-SPEC.md) — 如何编写自定义插件
- [插件生态架构](docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md) — 插件系统设计
- [架构文档](docs/ARCHITECTURE.md) — 系统整体架构

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI · SQLModel · LiteLLM · SQLite / PostgreSQL |
| 前端 | React · Vite · Zustand · TypeScript · Tailwind CSS v4 · shadcn/ui（Radix） |
| 数据 | SQLite（本地）· PostgreSQL（生产）· IndexedDB（浏览器离线） |
| AI | 任意 LiteLLM 兼容 LLM · 独立图片生成 API |
| 工具链 | mise · uv · ruff |
