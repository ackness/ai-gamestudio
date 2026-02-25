---
name: social
description: NPC 关系、阵营声望与社交关系追踪。
when_to_use:
  - 玩家与 NPC 进行有意义的互动
  - 玩家行为影响了某个阵营的好感度
  - 需要展示当前关系或声望状态
avoid_when:
  - 纯环境描写无 NPC 互动
  - 行为不涉及任何阵营立场
---

## Social Plugin

管理 NPC 关系与阵营声望的结构化变化。

### 工作流程
1. 从上下文读取当前关系状态。
2. 调用 `emit.items` 输出 `relationship_change` 与/或 `reputation_change`。
3. 按需写入存储，保持长期一致性。

### 示例
```json
{
  "items": [
    {"type": "relationship_change", "data": {"npc_name": "王掌柜", "change": 10, "reason": "玩家帮助修复酒馆", "new_level": 60, "rank": "友好", "relationship_type": "friend"}},
    {"type": "reputation_change", "data": {"faction": "港务会", "change": 8, "reason": "协助处理走私", "new_standing": 35, "rank": "友好"}}
  ]
}
```
