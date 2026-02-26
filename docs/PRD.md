# Product Requirements Document (PRD)

## 1. 产品定位

AI GameStudio 是一个以 LLM 驱动的可扩展文字 RPG 平台：

- 用 Markdown 描述世界观
- 用聊天推进剧情
- 用插件处理机制化系统（战斗、状态、图鉴、图像等）

## 2. 产品目标

### 2.1 核心目标

1. 让用户在 5 分钟内创建可游玩的世界。
2. 支持长会话连续叙事与状态一致性。
3. 通过插件实现机制扩展且不破坏主叙事体验。

### 2.2 非目标

- 不做 3D 实时引擎。
- 不在前端硬编码复杂规则系统。
- 不维护多套插件版本协议。

## 3. 用户画像

- 世界构建者：关注设定与剧情沉浸。
- 机制玩家：关注战斗、资源、成长反馈。
- 内容创作者：关注章节化导出、图像素材、复盘能力。

## 4. 核心用户流程

1. 创建项目并编辑世界文档。
2. 启动会话，输入玩家行动。
3. 主 LLM 生成叙事文本。
4. Plugin Agent 触发结构化机制输出。
5. 前端展示 block 卡片（选项、战斗、图鉴、图片等）。
6. 持续推进并在需要时归档/恢复。

## 5. 功能需求

## 5.1 世界文档系统

- 支持 Markdown 编辑与模板快速创建。
- 支持 frontmatter（name/genre/tags/plugins）。
- 支持项目级保存和复用。

验收标准：

- frontmatter 修改可持久化。
- `plugins` 默认启用行为生效。

## 5.2 回合聊天系统

- 支持 WebSocket 流式输出。
- 支持 HTTP fallback。
- 支持阶段事件（`phase_change: plugins/complete`）与会话阶段切换（`init/character_creation/playing`）。

验收标准：

- 长回复可稳定流式展示。
- 会话刷新后能恢复历史消息与 block。

## 5.3 插件系统（规范 v1）

- 插件必需双文件：`manifest.json + PLUGIN.md`。
- 仅支持 `schema_version: "1.0"`。
- 支持依赖、默认启用、supersedes、runtime settings。

验收标准：

- `plugin:validate` 全部通过。
- 无 fallback 路径或多版本判断分支。

## 5.4 Plugin Agent

- 独立模型调用，按插件并行执行。
- 工具固定为 6 个：
  - `emit`
  - `db_read`
  - `db_log_append`
  - `db_log_query`
  - `db_graph_add`
  - `execute_script`

验收标准：

- 插件可以在 1~N 轮工具调用内完成机制输出。
- 工具调用失败会返回可见错误反馈且不中断主流程。

## 5.5 状态与数据

- 角色、场景、事件、消息持久化。
- 插件存储使用 `(project_id, plugin_name, key)` 隔离。
- 关键 block 执行后可更新 DB 与前端 UI。

验收标准：

- 同项目跨会话数据可追溯。
- 插件状态互不污染。

## 5.6 记忆与归档

- memory 插件负责自动归档、摘要压缩、版本恢复。
- 支持手动恢复和分叉恢复。

验收标准：

- 归档版本可列出。
- 指定版本恢复后状态一致。

## 5.7 图片生成

- 通过 `image` 插件触发 `story_image` block。
- 支持连续性参考图。
- 支持失败重试。

验收标准：

- 图片生成失败不影响主叙事。
- 历史图片可回看与复用。

## 6. 非功能需求

- 稳定性：插件异常不应导致整轮崩溃。
- 可观测性：关键插件执行写入 debug/audit。
- 安全性：脚本路径不可越界，API Base 必须经过安全检查。
- 性能：常规回合插件阶段延迟控制在可交互范围。

## 7. 指标

- 会话完成率
- 每会话平均回合数
- 插件触发成功率
- block 校验通过率
- 用户重返率（D1/D7）

## 8. 里程碑

### M1：基础可玩

- 世界编辑、会话聊天、核心插件（database/state/event）

### M2：机制扩展

- combat/inventory/social + runtime settings

### M3：内容增强

- codex/image + 小说生成 + 归档恢复完善

## 9. 风险与缓解

- LLM 不稳定输出：加强 block schema 校验 + 失败兜底通知。
- 插件脚本风险：脚本沙箱与审计日志。
- 长上下文成本：memory 压缩与分层注入。

## 10. 版本声明

本 PRD 与当前实现保持一致，插件规范为单版本 v1。
