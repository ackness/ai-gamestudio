## 图鉴知识库

{% set plugin_storage = plugin_storage | default({}, true) %}
{% set runtime_settings = runtime_settings | default({}, true) %}

{% if plugin_storage.get('codex-entries') %}
玩家已发现的知识条目：

{% set entries = plugin_storage['codex-entries'] %}
{% set categories = {'monster': '怪物', 'item': '物品', 'location': '地点', 'lore': '传说', 'character': '角色'} %}
{% for cat_key, cat_name in categories.items() %}
{% set cat_entries = entries | selectattr('category', 'equalto', cat_key) | list %}
{% if cat_entries %}
### {{ cat_name }}
{% for e in cat_entries %}
{% if runtime_settings.get('codex_detail', 'detailed') == 'detailed' %}
- 【{{ e.title }}】{{ e.content }}{% if e.tags %}（{{ e.tags | join('、') }}）{% endif %}
{% else %}
- 【{{ e.title }}】{{ e.content[:50] }}…
{% endif %}
{% endfor %}
{% endif %}
{% endfor %}

请基于玩家已知信息叙事，避免重复解释已知内容。
如出现新知识点，调用 `emit` 输出 `codex_entry`（action=unlock/update）。
{% else %}
玩家尚未发现图鉴条目。遇到新怪物、物品、地点或传说时，调用 `emit` 输出 `codex_entry`。
{% endif %}
