---
name: combat
description: 统一战斗系统：回合制战斗、骰子判定、技能检定与状态效果。
when_to_use:
  - 玩家与敌人发生战斗
  - 需要随机判定（攻击/防御/技能检定）
  - 玩家尝试需要判定的技能行动
  - 角色被施加增益或减益效果
avoid_when:
  - 纯叙事无战斗或检定
  - 结果已经确定的行动
---

## Combat Plugin

Merged from: combat + skill-check + dice-roll + status-effect

### 工作流程
1. 阅读上下文中的角色数据（已提供，无需 db_read）
2. 如需随机判定，调用 execute_script 掷骰
3. 用 update_and_emit 一次完成角色属性更新 + 战斗日志 + 前端通知

### 示例：战斗结算
```
update_and_emit({
  "writes": [
    {"collection": "characters", "key": "角色名", "value": {"name": "...", "attributes": {"气血": 80}, "inventory": [...]}}
  ],
  "logs": [
    {"collection": "combat_log", "entry": {"participants": [...], "outcome": "...", "damage": 20}}
  ],
  "emits": [
    {"type": "dice_result", "data": {"expression": "2d6+3", "result": 11}},
    {"type": "combat_action", "data": {"attacker": "...", "target": "...", "damage": 20}}
  ]
})
```

### Dice Rolling (json:dice_result)
当需要随机判定时输出。重大判定建议使用 execute_script 调用 dice.roll。

### Skill Checks (json:skill_check / json:skill_check_result)
成功等级：critical_success / success / failure / critical_failure。

### Turn-Based Combat
- json:combat_start — 声明参战者
- json:combat_action — 声明行动，触发解算
- json:combat_round — 系统自动生成结果
- json:combat_end — 结束战斗

### Status Effects (json:status_effect)
管理 buff/debuff/dot/hot 效果。回合结束可调用 status_effect.tick 批量结算。
