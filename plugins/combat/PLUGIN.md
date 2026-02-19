---
name: combat
version: 2.0.0
description: 回合制战斗系统，支持攻击、防御、技能和逃跑行动。
when_to_use:
  - 玩家与敌人发生战斗
  - 需要回合制战斗解算
  - 遭遇战、Boss 战等战斗场景
avoid_when:
  - 纯叙事无战斗
  - 非战斗的技能检定（使用 skill-check 插件）
  - 社交或探索场景
capability_summary: |
  提供完整的回合制战斗系统。通过 json:combat_start 开始战斗，
  json:combat_action 声明行动，combat.resolve_action 解算结果，
  json:combat_end 结束战斗。
---

# Purpose
管理回合制战斗遭遇，提供攻击判定、伤害计算和战斗状态追踪。

# Capabilities
- combat.resolve_action: 解算战斗行动（攻击骰 vs 防御、伤害骰），返回回合结果

# Direct Blocks

## json:combat_start
当战斗开始时，声明参战者列表：

```json:combat_start
{"combatants": [{"name": "勇者", "hp": 30, "initiative": 18}, {"name": "哥布林", "hp": 12, "initiative": 8}], "description": "哥布林从灌木丛中跳出！"}
```

必需字段：combatants（数组，每项含 name, hp, initiative）。可选字段：description。

## json:combat_action
声明战斗行动，触发系统解算：

```json:combat_action
{"actor": "勇者", "action_type": "attack", "target": "哥布林", "weapon": "长剑", "attack_bonus": 5, "defense": 12, "damage_dice": "1d8+3", "description": "挥剑斩向哥布林"}
```

必需字段：actor, action_type, target。action_type 可选值：attack, defend, skill, flee。

## json:combat_round
由系统自动生成，包含行动解算结果。不要手动输出。

## json:combat_end
当战斗结束时输出：

```json:combat_end
{"outcome": "victory", "survivors": ["勇者"], "rewards": {"xp": 50, "items": ["哥布林短刀"]}, "description": "战斗胜利！"}
```

必需字段：outcome（victory/defeat/flee/truce）。可选字段：survivors, rewards, description。

# Rules
- 战斗开始必须先输出 combat_start
- 每个行动独立输出一个 combat_action block
- 战斗结束必须输出 combat_end
- 按先攻顺序（initiative）处理行动
- 不要在非战斗场景中使用战斗 block
- 重要战斗行动建议使用 plugin_use 调用 combat.resolve_action 以确保公正
