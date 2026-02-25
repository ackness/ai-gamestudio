---
name: event
description: 事件追踪与任务管理系统。
when_to_use:
  - NPC 给予新任务时
  - 任务目标有进展时
  - 任务完成或失败时
  - 玩家接受任务、发现线索、触发剧情事件时
avoid_when:
  - 纯叙事无任务或事件相关内容
---

## Event Plugin

用于追踪事件生命周期与任务进度。

### 工作流程
1. 读取上下文中的事件/任务状态。
2. 调用 `emit` 输出结构化结果，并按需写入存储。

### 示例
```json
{
  "items": [
    {"type": "event", "data": {"action": "create", "event_type": "quest", "name": "调查失踪案", "description": "城北出现失踪人口"}},
    {"type": "quest_update", "data": {"action": "create", "quest_id": "q_missing", "title": "调查失踪案", "status": "active"}}
  ]
}
```

### 输出约束
- `event.action`：`create / evolve / resolve / end`
- `quest_update.action`：`create / update / complete / fail`
- `quest_update.status`：`active / completed / failed`

### 规则
- 每个创建事件都应最终收束（`resolve` 或 `end`）。
- 任务推进要和叙事一致，不制造空进度。
