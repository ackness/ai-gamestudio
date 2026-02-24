# Tech Stack

## 1. 总览

| 层 | 技术 |
|---|---|
| 后端 | FastAPI, SQLModel, LiteLLM, Loguru |
| 前端 | React, TypeScript, Zustand, Tailwind CSS, shadcn/ui |
| 数据 | SQLite（默认）, PostgreSQL（可选）, IndexedDB（前端兜底） |
| AI | 任意 LiteLLM 兼容模型 + 独立图像生成 API |
| 工具链 | mise, uv, ruff, pytest |

## 2. 后端关键模块

| 模块 | 文件 | 作用 |
|---|---|---|
| API 层 | `backend/app/api/*.py` | 路由与输入输出校验 |
| 回合编排 | `backend/app/services/chat_service.py` | 主流程、阶段切换、消息落库 |
| 上下文装配 | `backend/app/services/turn_context.py` | 会话上下文聚合 |
| 插件代理 | `backend/app/services/plugin_agent.py` | 插件并行工具调用 |
| 插件引擎 | `backend/app/core/plugin_engine.py` | 发现/加载/校验/依赖排序 |
| Manifest 解析 | `backend/app/core/manifest_loader.py` | schema v1 校验 |
| Block 调度 | `backend/app/core/block_handlers.py` | builtin + 声明式处理 |

## 3. 前端关键模块

| 模块 | 文件 | 作用 |
|---|---|---|
| API 客户端 | `frontend/src/services/api.ts` | HTTP 请求封装 |
| WebSocket | `frontend/src/services/websocket.ts` | 实时消息通信 |
| 插件状态 | `frontend/src/stores/pluginStore.ts` | 插件列表与开关状态 |
| 游戏状态 | `frontend/src/stores/gameStateStore.ts` | 角色/事件/场景状态 |
| 插件面板 | `frontend/src/components/plugins/PluginPanel.tsx` | 插件配置 UI |
| Block 渲染 | `frontend/src/blockRenderers.ts` | 自定义渲染器注册 |

## 4. 插件技术栈（v1）

### 4.1 插件结构

```text
plugins/<group>/<plugin>/
  manifest.json
  PLUGIN.md
  prompts/
  scripts/
  schemas/
```

### 4.2 manifest schema

- 版本：`schema_version = "1.0"`
- 必需字段：`name/version/type/required/description`
- 运行时扩展：`blocks/capabilities/storage/extensions/...`

### 4.3 Plugin Agent 工具

- `update_and_emit`
- `emit_block`
- `db_read`
- `db_log_append`
- `db_log_query`
- `db_graph_add`
- `execute_script`

## 5. 测试与质量

| 类型 | 命令 |
|---|---|
| 后端测试 | `mise run test:backend` |
| 前端测试 | `mise run test:frontend` |
| 插件校验 | `mise run plugin:validate` |
| 插件测试脚本 | `mise run plugin:test` |
| 插件 dry-run | `mise run plugin:test:dry-run` |
| Lint | `mise run lint` |

## 6. 运行环境

- Python 3.12
- Node 22
- uv 虚拟环境
- 默认 SQLite：`data/db.sqlite`

## 7. 部署形态

- 本地开发：`dev:backend + dev:frontend`
- Docker 单容器：后端静态托管前端
- Vercel：HTTP 模式 + 前端 IndexedDB 兜底

## 8. 版本说明

本文档对应当前主干代码，插件系统为单版本 v1。
