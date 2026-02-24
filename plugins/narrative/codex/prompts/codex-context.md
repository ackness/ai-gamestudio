## 图鉴知识库

{% if plugin_storage.get('codex-entries') %}
玩家已发现的知识条目：

{% set entries = plugin_storage['codex-entries'] %}
{% set categories = {'monster': '怪物', 'item': '物品', 'location': '地点', 'lore': '传说', 'character': '角色'} %}
{% for cat_key, cat_name in categories.items() %}
{% set cat_entries = entries | selectattr('category', 'equalto', cat_key) | list %}
{% if cat_entries %}
### {{ cat_name }}
{% for e in cat_entries %}
{% if settings.codex_detail == 'detailed' %}
- 【{{ e.title }}】{{ e.content }}{% if e.tags %}（{{ e.tags | join('、') }}）{% endif %}
{% else %}
- 【{{ e.title }}】{{ e.content[:50] }}…
{% endif %}
{% endfor %}
{% endif %}
{% endfor %}

请基于玩家已知的图鉴内容来叙事，不要重复解释玩家已经了解的信息。
当玩家遇到新事物时，记得输出 codex_entry block。
{% else %}
玩家尚未发现任何图鉴条目。当玩家遇到新怪物、物品、地点或传说时，请输出 codex_entry block。
{% endif %}
