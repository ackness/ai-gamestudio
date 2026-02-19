---
name: quest
version: 2.0.0
description: 任务追踪与管理系统。
when_to_use:
  - NPC 给予新任务时
  - 任务目标有进展时
  - 任务完成或失败时
  - 需要展示当前活跃任务时
avoid_when:
  - 纯叙事无任务相关内容
  - 闲聊对话
capability_summary: |
  纯声明式任务系统。通过 json:quest_update block 创建、
  更新、完成或失败任务。任务数据通过 storage 持久化，
  活跃任务列表自动注入 LLM 上下文。
---

# Purpose
追踪和管理游戏中的任务，包括创建、更新进度、完成和失败。

# Direct Blocks

## json:quest_update
当任务状态发生变化时输出：

```json:quest_update
{"action": "create", "quest_id": "find-artifact", "title": "寻找失落的神器", "description": "在废墟中找到古代神器", "objectives": [{"id": "obj1", "text": "进入废墟", "completed": false}, {"id": "obj2", "text": "击败守卫", "completed": false}], "rewards": {"xp": 100, "gold": 50}, "status": "active"}
```

必需字段：action, quest_id, title, status。
可选字段：description, objectives, rewards。

action 取值：
- create — 创建新任务
- update — 更新任务进度（修改 objectives 的 completed 状态）
- complete — 任务完成
- fail — 任务失败

# Rules
- 每个任务必须有唯一的 quest_id
- 创建任务时应包含清晰的目标列表
- 更新时只需包含变化的字段
- 任务复杂度遵循 quest_complexity 设置
- 奖励显示遵循 show_rewards 设置
