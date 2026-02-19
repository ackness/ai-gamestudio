---
name: relationship
version: 2.0.0
description: 追踪 NPC 与玩家的关系变化，包括好感度与关系类型。
when_to_use:
  - 玩家与 NPC 进行有意义的互动（帮助、对抗、赠礼、对话选择）
  - NPC 对玩家的态度因事件发生改变
  - 需要展示当前关系状态
avoid_when:
  - 纯环境描写无 NPC 互动
  - NPC 仅作为背景出现未与玩家交互
capability_summary: |
  追踪每个 NPC 与玩家的好感度（0-100）和关系类型，
  在关系发生变化时输出 json:relationship_change block。
---

# Purpose
管理玩家与 NPC 之间的关系状态，记录好感度变化与关系类型转变。

# Direct Blocks

## json:relationship_change
当 NPC 与玩家的关系发生显著变化时输出此 block：

```json:relationship_change
{"npc_name": "艾琳", "change": 15, "reason": "帮助她找回了丢失的护身符", "new_level": 65, "rank": "友好", "relationship_type": "friend"}
```

必需字段：npc_name, change, reason, new_level, rank, relationship_type。

### 好感等级（rank）
- 亲密（80-100）：深厚的信任与羁绊
- 友好（60-79）：积极正面的关系
- 中立（40-59）：普通往来
- 冷淡（20-39）：疏远或不信任
- 敌对（0-19）：明确的敌意

### 关系类型（relationship_type）
- friend：朋友/同伴
- rival：竞争对手
- romantic：恋人/暧昧
- mentor：师徒关系
- enemy：敌人

# Rules
- 每次关系变化独立输出一个 relationship_change block
- change 值应合理反映互动的影响程度（通常 ±5 到 ±20）
- 重大事件（救命、背叛）可以有更大的变化幅度
- 不要在没有实质互动时输出关系变化
- new_level 必须在 0-100 范围内
- rank 必须与 new_level 对应的区间一致
