{% if memories %}
## Memory Context

Use these memories for consistency with prior story state:
{% for memory in memories %}
- {% if memory.timestamp %}[{{ memory.timestamp }}] {% endif %}{{ memory.content }}
{% endfor %}
{% endif %}
