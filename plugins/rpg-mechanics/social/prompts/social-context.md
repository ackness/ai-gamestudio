## NPC 关系状态

{% if plugin_storage.get('npc-relationships') %}
当前玩家与 NPC 的关系：

{% for rel in plugin_storage['npc-relationships'] if rel is mapping %}
- {{ rel.npc_name }}：{{ rel.rank }}（好感度 {{ rel.new_level }}）— {{ rel.relationship_type }}
{% endfor %}

请根据以上关系状态调整 NPC 的对话语气和行为态度。
{% else %}
暂无已建立的 NPC 关系记录。
{% endif %}

{% if settings.relationship_depth == 'rich' %}
在描写 NPC 互动时，请体现关系深度：包括 NPC 的情感反应、称呼变化、特殊对话选项等。
{% endif %}

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
