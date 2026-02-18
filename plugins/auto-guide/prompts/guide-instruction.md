{% set g = runtime_settings.get('auto-guide', {}) if runtime_settings else {} %}
每次叙事回复末尾**必须**附加 `json:guide`（含 `json:character_sheet` 时不输出）：

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
