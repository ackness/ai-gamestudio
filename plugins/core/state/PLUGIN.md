---
name: state
description: 核心状态管理：状态同步、角色卡、场景更新、通知与角色上下文注入。
when_to_use:
  - 任何涉及角色/世界/场景状态变化的回合
  - 需要角色/NPC/场景上下文时（始终启用）
  - 需要向玩家显示重要提示时
avoid_when:
  - 纯对话无状态变化且无场景移动
---

## State Plugin

核心状态管理插件，通常作为全局基础能力启用。

### 工作流程
1. 从上下文读取当前角色、场景与世界状态（无需重复查询）。
2. 使用一次 `emit` 完成写入与输出：
   - `writes` 持久化状态变更
   - `items` 输出 `state_update / character_sheet / scene_update / notification`

### 示例调用
```json
{
  "writes": [
    {"collection": "characters", "key": "hero", "value": {"name": "Ayla", "attributes": {"hp": 92}}}
  ],
  "items": [
    {"type": "state_update", "data": {"characters": [{"name": "Ayla", "attributes": {"hp": 92}}]}},
    {"type": "notification", "data": {"level": "info", "content": "你在战斗后恢复了状态"}}
  ]
}
```

### 输出约束
- `state_update`：至少包含 `characters` 或 `world`。
- `character_sheet`：仅角色创建阶段使用；`data.name` 必填。
- `scene_update`：`action=move` 时 `name` 必填。
- `notification`：`data.content` 必填，`level` 为 `info/warning/success/error`。

### 规则
- 只提交本回合真实发生的增量。
- 已有玩家角色后，不再输出 `character_sheet`。
- 无状态变化时不输出结构化项。
