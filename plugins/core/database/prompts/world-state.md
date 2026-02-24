## Runtime State Snapshot

Project: {{ project.name }}

{% if current_scene %}
Current scene: {{ current_scene.name }}{% if current_scene.description %} - {{ current_scene.description }}{% endif %}
{% endif %}

{% if active_events %}
Active events:
{% for event in active_events %}
- [{{ event.event_type }}] {{ event.name }} ({{ event.status }}) [id: {{ event.id }}]{% if event.description %}: {{ event.description }}{% endif %}
{% endfor %}
{% endif %}

{% if world_state and world_state.project_name %}
World state source: {{ world_state.project_name }}
{% endif %}
