{% set g = runtime_settings.get('guide', {}) if runtime_settings else {} %}
{% set mode = g.get('guide_mode', 'guide') %}

{% if mode == 'guide' %}
每次叙事回复末尾**必须**附加 `json:guide`（以下情况不输出：含 `json:character_sheet`、开场叙事、用户消息明确要求不输出时）：

```json:guide
{
  "categories": [
    {"style": "safe", "suggestions": ["具体行动"]},
    {"style": "aggressive", "suggestions": ["具体行动"]}
  ]
}
```

- 类别数 {{ g.get('category_count', 3) }}，按场景选用：safe / aggressive / creative / wild
- 风格：{{ g.get('suggestion_style', 'concise') }}，含 wild：{{ g.get('include_wild_category', true) }}
- 每条 ≤20 字，口语化，是角色可立即执行的行动
- 禁止输出 `json:choices`
{% else %}
当叙事到达需要玩家做出明确选择的关键节点时，请在回复末尾附加 `json:choices`：

```json:choices
{
  "prompt": "简短描述当前需要做出的选择",
  "type": "single",
  "options": ["选项A", "选项B", "选项C"]
}
```

- 目标选项数量：{{ g.get('option_count', 3) }}
- 选项风格偏好：{{ g.get('option_style', 'balanced') }}
- 仅在叙事自然要求玩家做出决定时使用
- 如包含 `json:character_sheet` 则不输出
{% endif %}
