---
name: faction
version: 2.0.0
description: 阵营声望追踪系统，管理玩家与各阵营的关系等级。
when_to_use:
  - 玩家行为影响了某个阵营的好感度
  - 完成阵营相关任务或做出阵营立场选择
  - 帮助或伤害某阵营的NPC
  - 需要展示当前阵营关系状态
avoid_when:
  - 纯叙事无阵营互动
  - 行为不涉及任何阵营立场
capability_summary: |
  纯声明式插件，无脚本能力。通过 json:reputation_change block
  记录声望变化，自动写入存储并触发事件。
---

# Purpose
追踪玩家与游戏世界中各阵营的声望关系，提供等级化的声望系统。

# Direct Blocks

## json:reputation_change
当玩家的行为影响了某个阵营的声望时，输出此 block：

```json:reputation_change
{"faction": "精灵议会", "change": 10, "reason": "帮助精灵使者传递密信", "new_standing": 35, "rank": "友好"}
```

必需字段：faction, change, reason, new_standing, rank。

声望等级参考：
- 崇拜 (>= 80)
- 尊敬 (>= 50)
- 友好 (>= 20)
- 中立 (-19 ~ 19)
- 冷淡 (<= -20)
- 敌对 (<= -50)
- 仇恨 (<= -80)

# Rules
- 每次声望变化独立输出一个 reputation_change block
- change 为正数表示声望提升，负数表示下降
- new_standing 应反映变化后的总声望值
- rank 应与 new_standing 对应的等级一致
- 不要在无阵营互动的纯叙事中输出此 block
