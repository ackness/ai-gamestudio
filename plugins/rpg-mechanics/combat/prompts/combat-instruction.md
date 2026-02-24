## 掷骰指令

当叙事中需要用随机性决定结果时（如战斗命中、技能检定、运气判定），
请在回复末尾附加一个 `json:dice_result` 代码块。

规则：
- 仅在需要随机判定时使用，不要每次回复都掷骰
- `dice` 字段使用标准骰子表达式（如 1d20, 2d6+3, 1d100）
- `result` 为计算后的数值
- `success` 根据上下文判定是否成功
- `description` 用简短的话描述这次投掷的意义

## 技能检定指令

当玩家尝试需要判定结果的技能行动时（如潜行、说服、攀爬、开锁、察觉、医疗等），
请在回复末尾附加一个 `json:skill_check` 代码块来请求检定。

规则：
- 仅在行动结果不确定、需要随机判定时使用
- `skill` 字段为技能名称（如 stealth, persuasion, athletics, lockpicking）
- `difficulty` 为难度等级（DC），范围 5-30
- `modifier` 为角色技能修正值（可选，默认 0）
- `attribute_bonus` 为属性加值（可选，默认 0）

系统会自动执行检定并返回 `json:skill_check_result`。

## 战斗系统指令

当叙事中发生战斗遭遇时，使用以下 block 管理战斗流程。

### 开始战斗
输出 `json:combat_start` 声明参战者（按先攻排序）。

### 战斗行动
每个回合为每个行动者输出 `json:combat_action`。系统会自动解算并返回 `json:combat_round` 结果。

### 结束战斗
当战斗结束时输出 `json:combat_end`。

### 规则
- 战斗必须以 combat_start 开始，以 combat_end 结束
- 按先攻顺序处理行动
- 非战斗场景不要使用战斗 block

## 活跃状态效果

{% set effects = storage.get('active-effects', []) %}
{% if effects %}
当前角色身上的状态效果：
{% for e in effects %}
- {{ e.effect_name }}（{{ e.effect_type }}）：{{ e.description }}，剩余 {{ e.duration }} 回合{% if e.damage_per_turn %}，每回合 {{ e.damage_per_turn }} 伤害{% endif %}{% if e.heal_per_turn %}，每回合 {{ e.heal_per_turn }} 治疗{% endif %}{% if e.stats %} | 属性修改：{% for k, v in e.stats.items() %}{{ k }}{{ '+' if v > 0 }}{{ v }}{% if not loop.last %}, {% endif %}{% endfor %}{% endif %}

{% endfor %}
{% else %}
当前无活跃状态效果。
{% endif %}

当需要施加/移除状态效果时，输出 `json:status_effect` block。
回合结束时可调用 `status_effect.tick` 能力批量结算效果。
