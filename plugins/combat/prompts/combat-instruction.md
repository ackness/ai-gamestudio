## 战斗系统指令

当叙事中发生战斗遭遇时，使用以下 block 管理战斗流程。

### 开始战斗
输出 `json:combat_start` 声明参战者（按先攻排序）：
- `combatants`：参战者数组，每项包含 name（名称）、hp（生命值）、initiative（先攻值）
- `description`：战斗开始的叙事描述

### 战斗行动
每个回合为每个行动者输出 `json:combat_action`：
- `actor`：行动者名称
- `action_type`：attack（攻击）、defend（防御）、skill（技能）、flee（逃跑）
- `target`：目标名称
- `weapon` / `skill`：使用的武器或技能名称
- `attack_bonus`：攻击加值
- `defense`：目标防御值（AC）
- `damage_dice`：伤害骰表达式（如 1d8+3）

系统会自动解算并返回 `json:combat_round` 结果。

### 结束战斗
当战斗结束时输出 `json:combat_end`：
- `outcome`：victory（胜利）、defeat（失败）、flee（逃跑）、truce（休战）
- `survivors`：存活者列表
- `rewards`：奖励（xp 经验值、items 物品）

### 规则
- 战斗必须以 combat_start 开始，以 combat_end 结束
- 按先攻顺序处理行动
- 每个行动独立输出一个 combat_action
- 根据 combat_round 结果推进叙事
- 非战斗场景不要使用战斗 block
