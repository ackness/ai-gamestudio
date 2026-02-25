## 战斗与检定指令（统一使用 emit）

当结果存在不确定性时，可调用能力（`execute_script`）完成判定，再通过 `emit.items` 输出结构化结果。

### dice_result
- 仅在需要随机判定时输出
- 记录骰式、结果和简要说明

### skill_check
- 当玩家行为需要技能检定时输出
- 需包含技能名和难度

### 战斗流程
- 开始战斗：输出 `combat_start`
- 执行动作：输出 `combat_action`（可触发解算能力）
- 回合结果：通常由系统能力回填 `combat_round`
- 结束战斗：输出 `combat_end`

### status_effect
施加、移除或结算状态效果时输出 `status_effect`。

## 活跃状态效果

{% set storage = storage | default({}, true) %}
{% set effects = storage.get('active-effects', []) %}
{% if effects %}
当前角色身上的状态效果：
{% for e in effects %}
- {{ e.effect_name }}（{{ e.effect_type }}）：{{ e.description }}，剩余 {{ e.duration }} 回合{% if e.damage_per_turn %}，每回合 {{ e.damage_per_turn }} 伤害{% endif %}{% if e.heal_per_turn %}，每回合 {{ e.heal_per_turn }} 治疗{% endif %}{% if e.stats %} | 属性修改：{% for k, v in e.stats.items() %}{{ k }}{{ '+' if v > 0 }}{{ v }}{% if not loop.last %}, {% endif %}{% endfor %}{% endif %}

{% endfor %}
{% else %}
当前无活跃状态效果。
{% endif %}
