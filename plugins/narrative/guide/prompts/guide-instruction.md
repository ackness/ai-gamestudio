{% set g = settings if settings else {} %}
{% if (not g) and runtime_settings %}
{% if runtime_settings.get('guide') %}
{% set g = runtime_settings.get('guide', {}) %}
{% elif runtime_settings.get('guide_mode') is not none %}
{% set g = runtime_settings %}
{% endif %}
{% endif %}
{% set mode = g.get('guide_mode', 'guide') %}

{% if mode == 'guide' %}
当需要给玩家提供行动建议时，调用 `emit`，在 `items` 中输出 `type=guide`。

建议要求：
- categories 数量：{{ g.get('category_count', 3) }}
- 建议风格：{{ g.get('suggestion_style', 'concise') }}
- 是否包含 wild：{{ g.get('include_wild_category', true) }}
- 每条建议应可立即执行，尽量简洁
- 调用模板：`emit({"items":[{"type":"guide","data":{"categories":[...]}}]})`
- 简例：`emit({"items":[{"type":"guide","data":{"categories":[{"style":"safe","suggestions":["先观察敌人动向"]}]}}]})`

当本回合正在创建角色时，不要输出 guide。
{% else %}
当剧情需要玩家做明确决策时，调用 `emit`，在 `items` 中输出 `type=choices`。

choices 要求：
- 选项数量目标：{{ g.get('option_count', 3) }}
- 选项风格偏好：{{ g.get('option_style', 'balanced') }}
- 仅在确实需要选择时输出
- 角色创建阶段不要输出 choices
- 调用模板：`emit({"items":[{"type":"choices","data":{"prompt":"...","type":"single","options":["选项A","选项B"]}}]})`
- 简例：`emit({"items":[{"type":"choices","data":{"prompt":"你要先做什么？","type":"single","options":["先调查港口","回客栈问线索","直接去城北"]}}]})`
- `options` 一项对应一个选项（纯文本），不要在一个字符串里拼接多个选项，不要使用 markdown。
{% endif %}
