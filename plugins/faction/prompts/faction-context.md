## 阵营声望

{% set standings = storage.get('faction-standings', {}) %}
{% set visibility = runtime_settings.get('reputation_visibility', 'fuzzy') %}
{% if standings %}
当前阵营关系：
{% for faction, info in standings.items() %}
{% if visibility == 'precise' %}
- {{ faction }}：{{ info.rank }}（声望值：{{ info.new_standing }}）
{% elif visibility == 'fuzzy' %}
- {{ faction }}：{{ info.rank }}
{% endif %}
{% endfor %}
{% else %}
尚未与任何阵营建立关系。
{% endif %}

当玩家行为影响阵营声望时，输出 `json:reputation_change` block。
