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
- 每个插件可注入提示词、定义自定义 Block 类型、写入游戏状态
- 内置 9 款插件（见下表）

### 世界观编辑器
- 左侧 Markdown 编辑器实时编辑世界文档
- 支持从模板一键创建（赛博朋克、黑暗奇幻、武侠、年代……）
- 支持 AI 自动生成世界文档

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
| `dice-roll` | 玩法 | 骰子结果 Block，带状态写入与事件触发 |
| `story-image` | 玩法 | 结构化提示词生成剧情图片，支持连续性 |

---

## 世界观模板

| 模板 | 风格 |
|------|------|
| `cyberpunk` | 赛博朋克都市，企业统治，黑客与增强人 |
| `dark-fantasy` | 黑暗奇幻，腐化神明，求生于末日世界 |
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
git clone <repo-url>
cd ai-gamestudio-v2

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

默认使用 **DeepSeek V3**（`deepseek-chat`），推荐理由：
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
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your-openai-key
```

### 使用 Ollama（本地模型）

```env
LLM_MODEL=ollama/qwen2.5:7b
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
| `LLM_MODEL` | 是 | `gpt-4o-mini` | LiteLLM 格式模型名 |
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
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your-api-key
```

- 数据存储在浏览器 IndexedDB，每个用户独立，刷新后保留，清除浏览器数据后丢失
- 前端会显示「临时存储」提示横幅

### 生产模式（接入 PostgreSQL）

```env
VITE_CHAT_TRANSPORT=http
VITE_API_BASE_URL=/api
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your-api-key
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>/<db>
CORS_ORIGINS=https://your-domain.vercel.app
```

推荐使用 [Neon](https://neon.tech) 或 [Supabase](https://supabase.com) 的免费 PostgreSQL。

---

## Docker 部署

项目使用 [mise](https://mise.jdx.dev/) 官方镜像作为基础，多阶段构建前端后合并到单一生产镜像。

### 快速启动（SQLite，单机）

```bash
# 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，填写 LLM_MODEL / LLM_API_KEY 等

# 构建并启动
docker compose up -d --build

# 访问
open http://localhost:8000
```

数据持久化在 Docker volume `ai-gamestudio-data`，重启不丢失。

### 生产部署（PostgreSQL）

```bash
# .env 中额外设置
POSTGRES_PASSWORD=your-strong-password

# 同时启动 app + postgres
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

### 常用操作

```bash
# 查看日志
docker compose logs -f

# 停止
docker compose down

# 重建镜像（代码有更新时）
docker compose up -d --build

# 备份 SQLite 数据
docker run --rm -v ai-gamestudio-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/data-backup.tar.gz /data
```

### 自定义端口

```bash
PORT=9000 docker compose up -d
```

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
ai-gamestudio-v2/
├── backend/
│   └── app/
│       ├── api/           # FastAPI 路由（projects, sessions, chat, plugins, templates）
│       ├── core/          # 框架内核（plugin_engine, prompt_builder, llm_gateway, block_parser）
│       ├── services/      # 业务逻辑（chat_service, plugin_service, runtime_settings_service）
│       └── models/        # SQLModel ORM 模型
├── frontend/
│   └── src/
│       ├── pages/         # ProjectListPage, ProjectEditorPage
│       ├── components/    # game/, editor/, plugins/, status/
│       ├── stores/        # Zustand 状态（session, gameState, project, plugin, ui）
│       └── services/      # api.ts, websocket.ts, settingsStorage.ts, localDb.ts
├── plugins/               # 内置插件
├── templates/worlds/      # 世界观模板
└── docs/                  # 详细文档
```

---

## 更多文档

- [插件规范 v2](docs/PLUGIN-SPEC.md) — 如何编写自定义插件
- [插件生态架构](docs/PLUGIN-ECOSYSTEM-ARCHITECTURE.md) — 插件系统设计
- [架构文档](docs/ARCHITECTURE.md) — 系统整体架构

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI · SQLModel · LiteLLM · SQLite / PostgreSQL |
| 前端 | React · Vite · Zustand · TypeScript |
| 数据 | SQLite（本地）· PostgreSQL（生产）· IndexedDB（浏览器离线） |
| AI | 任意 LiteLLM 兼容 LLM · 独立图片生成 API |
| 工具链 | mise · uv · ruff |
