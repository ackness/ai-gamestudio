## Story Image Guidance

{% set image_cfg = runtime_settings.get('image', {}) if runtime_settings else {} %}

{% if image_cfg.get('emit_mode', 'manual') == 'manual' %}
Do NOT output any `json:story_image` block. Image generation is handled manually by the player.
{% else %}
Use `json:story_image` only when the scene benefits from a visual frame.

Required block format:
```json:story_image
{
  "title": "Frame title",
  "story_background": "Recent narrative context.",
  "prompt": "Detailed visual for the current frame.",
  "continuity_notes": "Style and character continuity hints.",
  "reference_image_ids": ["optional-previous-image-id"],
  "layout_preference": "auto",
  "scene_frames": ["optional scene beat 1"]
}
```

Rules:
- `story_background` is mandatory.
- `prompt` must describe the present frame only.
- Include `reference_image_ids` from prior images for continuity.
- Style preset: {{ image_cfg.get('style_preset', 'cinematic') }}.
- Emission mode: {{ image_cfg.get('emit_mode', 'key_moments') }}.
- Multi-scene policy: {{ image_cfg.get('multi_scene_policy', 'comic') }}.
- Reference count: {{ image_cfg.get('reference_count', 2) }}.
- Strict continuity: {{ image_cfg.get('strict_continuity', true) }}.
- Skip if this turn includes `json:character_sheet`.

{% if image_cfg.get('emit_mode', 'manual') == 'every_turn' %}
Mandatory: append one `json:story_image` per narration response (except character creation).
{% else %}
Emit at major reveals, scene transitions, combat beats, or emotional close-ups.
{% endif %}

{% if story_images %}
Recent image references (newest last):
{% for image in story_images %}
- id={{ image.image_id }} | title={{ image.title }} | prompt={{ image.prompt }}
{% endfor %}
{% else %}
No previous image exists yet.
{% endif %}
{% endif %}
