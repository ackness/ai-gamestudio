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
| 回合编排 | `backend/app/services/chat_service.py` | 主流程、phase 事件、block 分发 |
| 上下文装配 | `backend/app/services/turn_context.py` | 会话上下文聚合、插件启用、runtime settings |
| 叙事提示组装 | `backend/app/services/prompt_assembly.py` | 叙事 prompt 组装（无 block 指令） |
| 插件代理 | `backend/app/services/plugin_agent.py` | 插件并行执行 + 工具循环 |
| 插件引擎 | `backend/app/core/plugin_engine.py` | 发现/加载/校验/依赖排序 |
| Manifest 解析 | `backend/app/core/manifest_loader.py` | schema v1 校验 + metadata 归一化 |
| Runtime Settings | `backend/app/services/runtime_settings_service.py` | schema 聚合、scope 校验、值解析 |
| Block 调度 | `backend/app/core/block_handlers.py` | builtin + 声明式 handler |

## 3. 前端关键模块

### 3.1 编排与传输

| 模块 | 文件 | 作用 |
|---|---|---|
| 游戏主面板 | `frontend/src/components/game/GamePanel.tsx` | 页面编排与交互入口 |
| WebSocket Hook | `frontend/src/hooks/useGameWebSocket.ts` | 连接生命周期、后端事件分发到 stores |
| 交互 Hook | `frontend/src/hooks/useGameActions.ts` | 发送消息/触发器/重试/retrigger |
| 传输层 | `frontend/src/services/websocket.ts` | WebSocket + HTTP fallback 双模式 |
| API 客户端 | `frontend/src/services/api.ts` | REST 请求封装 |

### 3.2 状态管理（Zustand）

| Store | 文件 | 核心状态 |
|---|---|---|
| 会话与消息 | `frontend/src/stores/sessionStore.ts` | messages、pendingBlocks、phase、pluginProgress |
| 游戏状态 | `frontend/src/stores/gameStateStore.ts` | characters、worldState、events |
| 插件面板 | `frontend/src/stores/pluginStore.ts` | 插件列表、enabled/conflict 信息 |
| Block Schema | `frontend/src/stores/blockSchemaStore.ts` | `/api/plugins/block-schemas` 缓存 |
| token 统计 | `frontend/src/stores/tokenStore.ts` | 每轮 token/cost 与累计消耗 |

### 3.3 Block 渲染层

| 模块 | 文件 | 作用 |
|---|---|---|
| 注册入口 | `frontend/src/blockRenderers.ts` | 注册自定义 block renderer |
| 渲染路由 | `frontend/src/services/blockRenderers.ts` | custom -> schema-generic -> fallback |
| 通用渲染器 | `frontend/src/components/game/GenericBlockRenderer.tsx` | schema 驱动 UI 渲染 |

## 4. 插件技术栈（v1）

### 4.1 插件结构

支持两种布局：

```text
plugins/<plugin>/
  manifest.json
  PLUGIN.md
```

```text
plugins/<group>/<plugin>/
  manifest.json
  PLUGIN.md
```

分组布局可附带 `plugins/<group>/group.json`。

### 4.2 manifest schema

- 版本：`schema_version = "1.0"`
- 必需字段：`name/version/type/required/description`
- 可扩展字段：`blocks/capabilities/storage/extensions/i18n/...`

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
| 插件测试（全部） | `mise run plugin:test:all` |
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
