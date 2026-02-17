# AI GameStudio（中文）

[English](README.en.md) | [首页](README.md)

LLM-Native 低代码 RPG 编辑器与运行平台。

> **WIP（开发中）：** 当前项目处于快速迭代阶段，API、插件行为与文档都可能频繁变化。

![AI GameStudio Full UI](.assets/full.png)

## AI GameStudio 是什么？

AI GameStudio 是一个基于 Web 的 LLM-Native 低代码 RPG 编辑器与运行平台。你不需要硬编码游戏逻辑，而是通过 Markdown 编写世界观规则，并通过文档驱动插件（`PLUGIN.md`）扩展玩法。

## 核心理念

- **世界观文档即源码**：用 Markdown 定义设定、规则、势力、叙事风格。
- **文档驱动插件系统**：插件声明在 `plugins/*/PLUGIN.md`，可配合模板/Schema/脚本扩展。
- **LLM 原生运行时**：采用 DM 协调式叙事与状态管理。
- **Block 协议（`json:<type>`）**：结构化输出由后端处理，再由前端组件渲染。

## 当前实现状态

- **前端**：React + Zustand，包含聊天/游玩界面、Block 渲染器、侧边状态面板。
- **后端**：FastAPI + SQLModel + SQLite，支持 WebSocket 流式输出。
- **插件运行时**：
  - 已实现：插件发现、校验、依赖排序、Prompt 注入、声明式 Block Action、请求级事件总线。
  - 预留位（可声明，但尚未形成完整通用执行框架）：`hooks`、插件级 `llm` 任务、`exports.commands/queries`。
- **归档系统**：内置必选 `archive` 插件，支持周期摘要与快照恢复。

架构基线见：`docs/ARCHITECTURE.md`（更新日期：2026-02-16）。

## 内置插件

- 必选：`core-blocks`、`database`、`character`、`archive`
- 可选：`memory`、`choices`、`dice-roll`、`auto-guide`

## 技术栈

- **前端**：Vite、React 19、TypeScript、Zustand、Tailwind CSS
- **后端**：FastAPI、SQLModel、SQLite（`aiosqlite`）、WebSocket
- **LLM 网关**：LiteLLM
- **工具链**：`mise` + `uv` + Node.js

详细说明见 `docs/TECH-STACK.md`。

## 快速开始

### 1. 前置条件

- 安装 [mise](https://mise.jdx.dev/)

### 2. 初始化

```bash
mise trust
mise install
cp .env.example .env
mise run setup
```

在 `.env` 中配置模型：

```env
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your-api-key-here
# LLM_API_BASE=...  # 可选，用于自定义网关/本地模型
```

### 3. 开发模式运行

建议使用两个终端：

```bash
mise run dev:backend
```

```bash
mise run dev:frontend
```

- 前端：`http://localhost:5173`
- 后端 API：`http://localhost:8000`
- 健康检查：`http://localhost:8000/api/health`

### 4. 本地生产模式运行

```bash
mise run start
```

然后访问 `http://localhost:8000`。

## 常用命令

```bash
mise run lint
mise run format
mise run plugin:validate
mise run plugin:list
mise run db:init
mise run db:reset
```

## 世界观模板

`templates/worlds/` 中已提供示例世界观：

- `wuxia.md`（武侠）
- `cyberpunk.md`（赛博朋克）
- `dark-fantasy.md`（黑暗奇幻）
- `epoch.md`（纪元）

## 文档导航

- 产品需求文档：`docs/PRD.md`
- 当前运行时架构：`docs/ARCHITECTURE.md`
- 插件规范：`docs/PLUGIN-SPEC.md`
- 技术栈与开发环境：`docs/TECH-STACK.md`
- 架构审查报告：`docs/ARCHITECTURE-REVIEW-2026-02-17.md`
