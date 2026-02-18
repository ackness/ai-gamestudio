# AI GameStudio（中文）

[首页（默认中文）](README.md) | [English](README.en.md)

把世界观写成文档，像聊天一样推进剧情，并在关键时刻生成剧情画面。

![image.png](.assets/image.png)

## 这张图里你看到的，就是项目核心

- 左侧是 `World Doc`：世界观、门派、规则直接写在 Markdown 里。
- 中间是 `Game Session`：玩家输入一句话，系统持续叙事并更新状态。
- 中间下方是剧情图片卡片：在关键场景输出 `story_image`，可直接重生成。
- 右侧是状态面板：角色、插件、设置、事件都在同一处查看和调节。
- 顶部和底部是实用操作：`Save / Restore / Debug / Sessions` 与回合输入框。

## 这次更新后的重点

- 插件现在有清晰的 `manifest.json`，依赖、Block、设置项都可被运行时直接识别。
- 新的故事图片链路更完整：生成、续帧参考、前端展示与重生成功能已经打通。
- 后端补齐了能力执行、脚本执行、审计日志等基础能力，便于排查与扩展。
- 插件启用状态、运行时设置与前端面板联动更稳定，调试体验更直接。

## 快速开始

1. 安装 [mise](https://mise.jdx.dev/)
2. 初始化项目：

```bash
mise trust
mise install
cp .env.example .env
mise run setup
```

3. 在 `.env` 里配置模型：

```env
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-api-key-here
LLM_API_BASE=https://api.deepseek.com
```

4. 启动开发环境（两个终端）：

```bash
mise run dev:backend
mise run dev:frontend
```

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`

## 常用命令

```bash
mise run test
mise run lint
mise run plugin:validate
mise run plugin:list
```

## 部署到 Vercel

项目已支持 Vercel 部署，线上默认建议使用 HTTP Chat 通道（不依赖 WebSocket）。

1. 在 Vercel 导入本仓库，直接部署即可（仓库内已提供 `vercel.json` 与 `app.py` 入口）。
2. 在 Vercel 项目环境变量中至少配置：

```env
# Frontend build-time
VITE_CHAT_TRANSPORT=http
VITE_API_BASE_URL=/api

# Backend runtime
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=your-api-key
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>/<db>
# CORS_ORIGINS=https://your-domain.vercel.app
```

3. 重新部署后访问站点即可体验。

说明：
- 如果不配置 `DATABASE_URL`，系统会在 Vercel 上回退到 `/tmp` 下的 SQLite，仅适合临时演示，不保证持久化。
- 如果启用了故事图片能力，还需要配置 `IMAGE_GEN_API_KEY`（以及可选 `IMAGE_GEN_MODEL` / `IMAGE_GEN_API_BASE`）。

## 目录速览

- `frontend/`：游戏界面与交互
- `backend/`：会话编排、插件运行时、API/WebSocket
- `plugins/`：内置插件（含 `story-image`）
- `templates/worlds/`：世界观模板

## 更多文档

- 架构：`docs/ARCHITECTURE.md`
- 插件规范：`docs/PLUGIN-SPEC.md`
- 产品需求：`docs/PRD.md`
