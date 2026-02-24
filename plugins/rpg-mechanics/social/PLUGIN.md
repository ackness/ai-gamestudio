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

### NPC Relationships (json:relationship_change)
追踪 NPC 与玩家的好感度（0-100）和关系类型。
好感等级：亲密(80-100) / 友好(60-79) / 中立(40-59) / 冷淡(20-39) / 敌对(0-19)

### Faction Reputation (json:reputation_change)
追踪玩家与各阵营的声望关系。
声望等级：崇拜(>=80) / 尊敬(>=50) / 友好(>=20) / 中立(-19~19) / 冷淡(<=-20) / 敌对(<=-50) / 仇恨(<=-80)
