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
