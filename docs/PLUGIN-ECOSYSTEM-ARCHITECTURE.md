# Plugin Ecosystem Architecture (v1)

本文档描述 AI GameStudio 当前插件生态的运行架构。这里的 v1 指插件规范版本（`schema_version: 1.0`），不是历史分支。

## 1. 内置插件版图

## 1.1 core

- `database`：持久状态上下文（required）
- `state`：角色/场景/通知/状态同步（required）
- `event`：事件与任务生命周期（required）
- `memory`：记忆、归档、自动压缩（default_enabled）

## 1.2 narrative

- `guide`：行动建议与交互选项（default_enabled）
- `codex`：图鉴百科
- `image`：剧情图片（default_enabled）

## 1.3 rpg-mechanics

- `combat`：战斗/检定/骰子/状态效果
- `inventory`：物品与装备
- `social`：关系与声望

## 2. 核心组件

| 组件 | 代码位置 | 职责 |
|---|---|---|
| PluginEngine | `backend/app/core/plugin_engine.py` | 插件发现、加载、校验、提示词注入、block/capability 声明提取 |
| ManifestLoader | `backend/app/core/manifest_loader.py` | `manifest.json` 解析与 schema v1 校验 |
| Plugin Agent | `backend/app/services/plugin_agent.py` | 回合后并行执行插件 LLM 调用与工具链 |
| Plugin Tools | `backend/app/core/plugin_tools.py` | 统一定义 7 个工具 |
| Block Dispatch | `backend/app/core/block_handlers.py` | block 校验后执行 builtin/声明式 handler |
| Plugin Service | `backend/app/services/plugin_service.py` | 项目维度启用状态、依赖补全、supersedes 抑制 |

## 3. 回合执行链路

1. 主 LLM 生成叙事文本。
2. `chat_service` 构建游戏状态快照。
3. `run_plugin_agent()` 对启用插件并行调用。
4. 每个插件通过工具完成状态写入、日志追加、脚本执行、block 输出。
5. block 经过 schema 校验后进入 `dispatch_block()`。
6. handler 执行存储写入/事件发送/builtin 处理。
7. 前端接收可展示 block（基础设施 block 如 `state_update` 可仅用于服务端处理）。

## 4. 工具调用模型

插件运行时仅可使用以下平台工具：

1. `update_and_emit`
2. `emit_block`
3. `db_read`
4. `db_log_append`
5. `db_log_query`
6. `db_graph_add`
7. `execute_script`

说明：

- 工具集合是固定契约。
- 旧工具名不再参与执行分支。

## 5. 插件状态与数据隔离

插件存储使用 `PluginStorage(project_id, plugin_name, key)` 三元组隔离。

- 不同项目隔离
- 不同插件隔离
- key 粒度可控

## 6. 安全边界

- `manifest.json` 必需，且 `schema_version` 必须为 `1.0`。
- prompt template 与脚本路径必须位于插件目录内。
- script capability 统一走 `PythonScriptRunner` 并记录审计日志。

## 7. 启用策略

最终启用集合来自：

- `required`
- `default_enabled`
- 世界文档 frontmatter
- 用户显式开关
- 依赖自动补全
- `supersedes` 抑制

## 8. API 接口概览

| 路由 | 说明 |
|---|---|
| `GET /api/plugins` | 列出插件元数据 |
| `POST /api/plugins/{name}/toggle` | 开关插件 |
| `GET /api/plugins/enabled/{project_id}` | 查询项目启用插件 |
| `GET /api/plugins/block-schemas` | 查询可渲染 block schema |
| `GET /api/plugins/block-conflicts` | 查询 block 冲突 |
| `POST /api/plugins/import/validate` | 校验待导入插件 |
| `POST /api/plugins/import/install` | 安装插件 |
| `GET /api/plugins/{name}/detail` | 获取插件详情 |
| `GET /api/plugins/{name}/audit` | 查询脚本审计 |

## 9. 运维与验证

常用命令：

```bash
mise run plugin:list
mise run plugin:validate
mise run plugin:test:list
mise run plugin:test:dry-run
```

## 10. 版本说明

- 本文档对应插件规范 v1。
- 代码与文档均按单版本维护，不再区分历史分支叙述。
