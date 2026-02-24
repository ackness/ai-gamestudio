---
name: event
description: 事件追踪与任务管理系统，合并自 core-blocks(event) 和 quest 插件。
when_to_use:
  - NPC 给予新任务时
  - 任务目标有进展时
  - 任务完成或失败时
  - 玩家接受任务、发现线索、触发剧情事件时
avoid_when:
  - 纯叙事无任务或事件相关内容
capability_summary: |
  提供 json:event 和 json:quest_update 两种 block 类型。
  event 追踪剧情事件生命周期，quest_update 管理任务创建与进度。
---

## Event & Quest Plugin

Merged from: core-blocks (event) + quest

### 工作流程
1. 阅读上下文中的游戏状态（已提供，无需 db_read）
2. 用 update_and_emit 一次完成所有事件/任务的 DB 写入 + 前端通知

### 示例：同时创建事件和任务
```
update_and_emit({
  "writes": [
    {"collection": "event", "key": "evt_001", "value": {"event_id": "evt_001", "event_type": "quest", "name": "...", "status": "active"}},
    {"collection": "quest", "key": "q_001", "value": {"quest_id": "q_001", "title": "...", "objectives": [...], "status": "active"}}
  ],
  "emits": [
    {"type": "event", "data": {"action": "create", "event_type": "quest", "name": "...", "description": "...", "visibility": "known"}},
    {"type": "quest_update", "data": {"action": "create", "quest_id": "q_001", "title": "...", "objectives": [...]}}
  ]
})
```

### Event Tracking (json:event)
Track quest/event lifecycle with actions: create, evolve, resolve, end.
Every created event MUST eventually resolve or end.

- `create`：玩家接受任务、发现线索、触发剧情事件时
- `evolve`：任务有重大进展时，需提供 event_id
- `resolve`：任务成功完成时，需提供 event_id
- `end`：任务失败或被放弃时，需提供 event_id

### Quest Management (json:quest_update)
- action: create / update / complete / fail
- 每个任务必须有唯一的 quest_id
- 创建任务时应包含清晰的目标列表
