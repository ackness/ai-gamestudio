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

### Event Tracking (json:event)

Track quest/event lifecycle with actions: create, evolve, resolve, end.
Every created event MUST eventually resolve or end.

**必须触发的场景：**
- `create`：玩家接受任务、发现线索、触发剧情事件时
- `evolve`：任务有重大进展时，需提供 event_id
- `resolve`：任务成功完成时，需提供 event_id
- `end`：任务失败或被放弃时，需提供 event_id

### Quest Management (json:quest_update)

Structured quest tracking with objectives, rewards, and status.

- action: create / update / complete / fail
- 每个任务必须有唯一的 quest_id
- 创建任务时应包含清晰的目标列表
- 任务复杂度遵循 quest_complexity 设置
- 奖励显示遵循 show_rewards 设置
