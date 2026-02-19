---
name: status-effect
version: 2.0.0
description: 状态效果系统，管理增益、减益、持续伤害与持续治疗。
when_to_use:
  - 角色被施加增益或减益效果
  - 中毒、灼烧等持续伤害效果
  - 治疗光环、再生等持续治疗效果
  - 回合结束时需要结算状态效果
avoid_when:
  - 纯叙事无战斗或状态变化
  - 一次性即时伤害或治疗（不需要持续效果）
capability_summary: |
  提供状态效果管理能力。可直接输出 json:status_effect block，
  或通过 json:plugin_use 调用 status_effect.tick 在回合结束时
  批量处理所有活跃效果。
---

# Purpose
管理角色身上的各类状态效果，包括增益(buff)、减益(debuff)、
持续伤害(DoT)和持续治疗(HoT)。

# Capabilities
- status_effect.tick: 处理回合结束时所有活跃效果的持续时间递减与伤害/治疗计算

# Direct Blocks

## json:status_effect
当需要施加、移除或触发状态效果时，输出此 block：

施加效果：
```json:status_effect
{"action": "apply", "effect_name": "中毒", "effect_type": "dot", "duration": 3, "target": "玩家", "damage_per_turn": 5, "description": "被毒蛇咬伤，每回合受到毒素伤害"}
```

移除效果：
```json:status_effect
{"action": "remove", "effect_name": "中毒", "effect_type": "dot", "duration": 0, "target": "玩家", "description": "毒素已被净化"}
```

增益效果（带属性修改）：
```json:status_effect
{"action": "apply", "effect_name": "战吼", "effect_type": "buff", "duration": 5, "target": "玩家", "stats": {"attack": 3, "defense": 1}, "description": "战吼激励，攻击和防御暂时提升"}
```

必需字段：action, effect_name, effect_type, target, description。
可选字段：duration, stats, damage_per_turn, heal_per_turn。

# Rules
- 每个状态效果独立输出一个 status_effect block
- apply 时必须指定 duration（持续回合数）
- buff/debuff 通常搭配 stats 字段
- dot 搭配 damage_per_turn，hot 搭配 heal_per_turn
- 回合结束时可通过 plugin_use 调用 status_effect.tick 批量结算
- 效果到期自动移除，无需手动输出 remove
