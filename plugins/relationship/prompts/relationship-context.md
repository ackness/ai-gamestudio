## NPC 关系状态

{% if plugin_storage.get('npc-relationships') %}
当前玩家与 NPC 的关系：

{% for rel in plugin_storage['npc-relationships'] if rel is mapping %}
- {{ rel.npc_name }}：{{ rel.rank }}（好感度 {{ rel.new_level }}）— {{ rel.relationship_type }}
{% endfor %}

请根据以上关系状态调整 NPC 的对话语气和行为态度。
好感度高的 NPC 更愿意帮助玩家、分享信息；好感度低的 NPC 可能冷淡、拒绝或敌对。
{% else %}
暂无已建立的 NPC 关系记录。随着玩家与 NPC 互动，关系将逐步建立。
{% endif %}

{% if settings.relationship_depth == 'rich' %}
在描写 NPC 互动时，请体现关系深度：包括 NPC 的情感反应、称呼变化、特殊对话选项等。
{% endif %}
