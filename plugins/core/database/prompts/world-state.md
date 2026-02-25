## Runtime State Snapshot

{% set project = project | default({}, true) %}
{% set current_scene = current_scene | default({}, true) %}
{% set active_events = active_events | default([], true) %}
{% set world_state = world_state | default({}, true) %}

Project: {{ project.get('name', 'Unknown') }}

{% if current_scene %}
Current scene: {{ current_scene.get('name', 'Unknown') }}{% if current_scene.get('description') %} - {{ current_scene.get('description') }}{% endif %}
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
