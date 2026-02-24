# System Architecture

AI GameStudio 采用“主叙事 LLM + 插件代理 LLM”的双层架构：

- 主 LLM 负责自然语言叙事。
- Plugin Agent 负责机制化处理（状态、战斗、任务、图鉴、图像等）。

## 1. 高层结构

```text
Frontend (React + Zustand)
        |
        | WebSocket / HTTP
        v
Backend (FastAPI)
  ├─ chat_service         # 回合主流程
  ├─ turn_context         # 上下文装配
  ├─ prompt_builder       # 主模型提示词组装
  ├─ plugin_agent         # 插件并行工具调用
  ├─ block_handlers       # block 调度执行
  ├─ plugin_engine        # 插件发现/加载/校验
  └─ plugin_service       # 启用状态与依赖管理
```

## 2. 一次回合的执行序列

1. 用户输入到达 `chat_service`。
2. `turn_context` 读取会话、项目、角色、场景、事件、插件状态等。
3. `prompt_builder` 组装主模型消息并请求主 LLM。
4. 主模型输出叙事内容。
5. `plugin_agent.run_plugin_agent()` 对启用插件并行调用。
6. 插件通过工具输出结构化 block。
7. `validate_block_data()` 校验 block。
8. `dispatch_block()` 执行 builtin/声明式 handler。
9. 前端实时渲染 block，服务端持久化状态。

## 3. 插件系统（v1）

### 3.1 文件规范

每个插件必须包含：

- `manifest.json`（机器契约）
- `PLUGIN.md`（LLM 操作手册）

`manifest.json` 必须满足 `schema_version: "1.0"`。

### 3.2 目录规范

- 分组目录：`plugins/<group>/<plugin>/...`
- 支持 group 元信息：`plugins/<group>/group.json`

### 3.3 插件启用规则

`plugin_service.get_enabled_plugins()` 会合并：

- required 插件
- world frontmatter `plugins`
- default_enabled 插件
- 用户显式开关
- 自动依赖补全
- supersedes 抑制规则

### 3.4 插件工具契约

Plugin Agent 工具固定为：

1. `update_and_emit`
2. `emit_block`
3. `db_read`
4. `db_log_append`
5. `db_log_query`
6. `db_graph_add`
7. `execute_script`

## 4. Block 管道

### 4.1 生成

插件通过 `emit_block` 或 `update_and_emit` 输出 block。

### 4.2 校验

`block_validation.validate_block_data()` 基于插件声明 schema 与基础约束校验。

### 4.3 调度

`dispatch_block()` 顺序：

1. 内建 handler（注册表）
2. 插件声明式 handler（`storage_write` / `emit_event` / `builtin`）
3. 无 handler 时透传给前端

## 5. 数据模型

核心表（SQLModel）：

- `Project`
- `Session`
- `Message`
- `Character`
- `Scene`
- `GameEvent`
- `PluginStorage`
- `GameKV` / `GameLog` / `GameGraph`

插件状态隔离键：`(project_id, plugin_name, key)`。

## 6. 前端架构

- 状态管理：Zustand（session/project/gameState/plugin/ui 等）
- 数据通道：WebSocket 为主，HTTP 兜底
- Block 渲染：
  - 已注册自定义渲染器
  - 通用 schema 渲染器（generic renderer）

## 7. 插件相关 API

- `GET /api/plugins`
- `POST /api/plugins/{name}/toggle`
- `GET /api/plugins/enabled/{project_id}`
- `GET /api/plugins/block-schemas`
- `GET /api/plugins/block-conflicts`
- `POST /api/plugins/import/validate`
- `POST /api/plugins/import/install`
- `GET /api/plugins/{name}/detail`
- `GET /api/plugins/{name}/audit`

## 8. 运维命令

```bash
mise run plugin:list
mise run plugin:validate
mise run plugin:test:list
mise run plugin:test:dry-run
```

## 9. 版本声明

本架构文档对应当前代码实现，插件规范为单版本 v1。
