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
capability_summary: |
  合并自 relationship + reputation + faction。
  提供 json:relationship_change 和 json:reputation_change block。
---

## Social Plugin

Merged from: relationship + reputation + faction

### 工作流程
1. 阅读上下文中的 NPC/阵营数据（已提供，无需 db_read）
2. 用 update_and_emit 一次完成关系更新 + 前端通知

### 示例：同时更新 NPC 关系和阵营声望
```
update_and_emit({
  "writes": [
    {"collection": "npc", "key": "NPC名", "value": {"name": "...", "affinity": 60, "relationship": "友好"}},
    {"collection": "world", "key": "faction_阵营名", "value": {"name": "...", "reputation": 30, "level": "友好"}}
  ],
  "emits": [
    {"type": "relationship_change", "data": {"npc_name": "...", "change": 10, "reason": "...", "new_level": 60, "rank": "友好"}},
    {"type": "reputation_change", "data": {"faction": "...", "change": 10, "new_level": 30, "rank": "友好"}}
  ]
})
```

### NPC Relationships (json:relationship_change)
追踪 NPC 与玩家的好感度（0-100）和关系类型。
好感等级：亲密(80-100) / 友好(60-79) / 中立(40-59) / 冷淡(20-39) / 敌对(0-19)

### Faction Reputation (json:reputation_change)
追踪玩家与各阵营的声望关系。
声望等级：崇拜(>=80) / 尊敬(>=50) / 友好(>=20) / 中立(-19~19) / 冷淡(<=-20) / 敌对(<=-50) / 仇恨(<=-80)
