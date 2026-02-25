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

管理战斗相关的结构化输出，并可调用脚本能力进行解算。

### 工作流程
1. 依据叙事决定是否需要判定/战斗流程。
2. 需要解算时调用 `execute_script`（如 `dice.roll`、`skill_check.resolve`）。
3. 使用 `emit` 输出战斗结构与状态变化。

### 示例
```json
{
  "logs": [{"collection": "combat_log", "entry": {"round": 3, "summary": "Ayla 命中哥布林"}}],
  "items": [
    {"type": "dice_result", "data": {"dice": "1d20+5", "result": 17, "success": true}},
    {"type": "combat_action", "data": {"actor": "Ayla", "action_type": "attack", "target": "Goblin"}}
  ]
}
```

### 规则
- 战斗流程建议：`combat_start -> combat_action -> combat_round -> combat_end`。
- `skill_check_result`、`combat_round` 通常由系统能力回填。
