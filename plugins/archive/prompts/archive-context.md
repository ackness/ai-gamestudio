{% if archive and archive.has_snapshot %}
## 存档摘要（压缩上下文）

当前激活版本：v{{ archive.active_version }}（最新版本：v{{ archive.latest_version }}）
{% if archive.title %}标题：{{ archive.title }}{% endif %}
{% if archive.turn %}对应回合：{{ archive.turn }}{% endif %}

### 摘要
{{ archive.summary }}

{% if archive.key_facts %}
### 关键事实
{% for item in archive.key_facts %}
- {{ item }}
{% endfor %}
{% endif %}

{% if archive.pending_threads %}
### 未完线索
{% for item in archive.pending_threads %}
- {{ item }}
{% endfor %}
{% endif %}

{% if archive.next_focus %}
### 建议推进方向
{% for item in archive.next_focus %}
- {{ item }}
{% endfor %}
{% endif %}

请保持叙事与以上状态一致。
{% endif %}
