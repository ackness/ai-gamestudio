# Plugin Ecosystem Architecture (v1)

本文档描述当前插件生态在后端与前端的实际运行方式。这里的 v1 指插件规范版本（`schema_version: 1.0`）。

## 1. 内置插件版图

### 1.1 `core`

- `database`：持久状态上下文（required）
- `state`：角色/场景/通知/状态同步（required）
- `event`：事件与任务生命周期（required）
- `memory`：记忆、归档、自动压缩（default_enabled）

### 1.2 `narrative`

- `guide`：行动建议与交互选项（default_enabled）
- `codex`：图鉴百科
- `image`：剧情图片（default_enabled）

### 1.3 `rpg-mechanics`

- `combat`：战斗/检定/骰子/状态效果
- `inventory`：物品与装备
- `social`：关系与声望

## 2. 生态核心组件

| 组件 | 代码位置 | 职责 |
|---|---|---|
| PluginEngine | `backend/app/core/plugin_engine.py` | 发现、加载、校验插件；提取 block/capability 声明 |
| ManifestLoader | `backend/app/core/manifest_loader.py` | `manifest.json` 解析与 v1 校验 |
| Plugin Agent | `backend/app/services/plugin_agent.py` | 回合后并行执行插件 LLM 与工具链 |
| Plugin Tools | `backend/app/core/plugin_tools.py` | 平台固定 7 工具定义 |
| Plugin Service | `backend/app/services/plugin_service.py` | 启用状态合并、依赖补全、supersedes 抑制 |
| Runtime Settings | `backend/app/services/runtime_settings_service.py` | 跨插件 runtime settings 聚合与合并 |
| Block Dispatch | `backend/app/core/block_handlers.py` | 校验后执行 builtin/声明式 handler |

## 3. 回合执行链路（插件视角）

1. 主 LLM 先输出叙事文本。
2. `chat_service` 触发 `phase_change: plugins`。
3. `run_plugin_agent()` 对启用插件并行执行，每插件最多 8 轮工具调用。
4. 运行中持续发 `plugin_progress`，结束后返回 `plugin_summary`。
5. 所有 block 进入 `validate_block_data()`。
6. 校验通过后进入 `dispatch_block()` 执行副作用。
7. 非基础设施 block 发给前端；`state_update` 等基础设施 block 仅服务端处理。
8. 本轮触发插件会更新 `plugin_trigger_counts`，用于 `max_triggers` 限流。

## 4. 前端对接链路（插件相关）

| 环节 | 前端代码 | 作用 |
|---|---|---|
| 连接管理 | `frontend/src/hooks/useGameWebSocket.ts` | 接收插件阶段事件并分发到 stores |
| 传输层 | `frontend/src/services/websocket.ts` | WebSocket/HTTP fallback 统一事件协议 |
| 进度状态 | `frontend/src/stores/sessionStore.ts` | `pluginProcessing/pluginProgress/lastPluginSummary` |
| schema 缓存 | `frontend/src/stores/blockSchemaStore.ts` | 缓存 `/api/plugins/block-schemas` |
| 渲染路由 | `frontend/src/services/blockRenderers.ts` | 自定义 renderer 与 schema renderer 选择 |

## 5. 工具调用模型

插件运行时仅可用以下平台工具：

1. `update_and_emit`
2. `emit_block`
3. `db_read`
4. `db_log_append`
5. `db_log_query`
6. `db_graph_add`
7. `execute_script`

说明：

- 工具集合固定，旧工具名不再参与执行分支。
- `execute_script` 通过 capability 声明映射到插件目录内脚本执行。

## 6. 插件状态隔离与存储

插件存储使用 `PluginStorage(project_id, plugin_name, key)` 三元组隔离。

- 项目隔离：不同项目互不影响
- 插件隔离：不同插件互不污染
- key 粒度：插件可自定义内部键空间

补充：

- runtime settings 使用独立存储命名空间插件名 `runtime-settings`。

## 7. 安全边界

- `manifest.json` 必需，且 `schema_version` 必须是 `1.0`。
- prompt template 与脚本路径必须在插件目录内（禁止越界路径）。
- script capability 统一走 `PythonScriptRunner`，可通过审计 API 查询记录。

## 8. 启用策略

最终启用集合由以下来源合并：

1. `required`
2. `default_enabled`
3. 世界文档 frontmatter `plugins`
4. 用户显式开关
5. 依赖自动补全
6. `supersedes` 抑制（用户显式启用可覆盖）

## 9. API 接口概览

| 路由 | 说明 |
|---|---|
| `GET /api/plugins` | 列出插件元数据 |
| `POST /api/plugins/{name}/toggle` | 开关插件 |
| `GET /api/plugins/enabled/{project_id}` | 查询项目启用插件 |
| `GET /api/plugins/block-schemas` | 查询 block UI schema |
| `GET /api/plugins/block-conflicts` | 查询 block 冲突 |
| `POST /api/plugins/import/validate` | 校验导入插件 |
| `POST /api/plugins/import/install` | 安装插件 |
| `GET /api/plugins/{name}/detail` | 获取插件详情 |
| `GET /api/plugins/{name}/audit` | 查询脚本审计 |

## 10. 运维与验证

```bash
mise run plugin:list
mise run plugin:validate
mise run plugin:test:list
mise run plugin:test:dry-run
```

## 11. 版本说明

- 本文档对应插件规范 v1。
- 代码与文档按单版本维护，不再区分历史分支叙述。
