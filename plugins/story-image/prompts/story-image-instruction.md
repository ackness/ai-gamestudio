## Story Image Guidance

{% set image_cfg = runtime_settings.get('story-image', {}) if runtime_settings else {} %}

Use `json:story_image` only when the scene benefits from a visual frame (major reveal, transition, combat beat, emotional close-up).

Required block format:

```json:story_image
{
  "title": "Frame title",
  "story_background": "Recent narrative context leading to this frame.",
  "prompt": "Detailed visual for the exact current frame.",
  "continuity_notes": "Style, character appearance, and object continuity hints.",
  "reference_image_ids": ["optional-previous-image-id"],
  "layout_preference": "auto",
  "scene_frames": ["optional scene beat 1", "optional scene beat 2"]
}
```

Rules:
- `story_background` is mandatory and must connect the frame to ongoing story.
- `prompt` must describe the present frame only, not future events.
- If prior image IDs are available, include them in `reference_image_ids` to keep continuity.
- Prior images are style/identity references, not a hard requirement to keep the same scene layout.
- Scene can change if current narration/prompt requests a new place or moment.
- Preferred style preset: {{ image_cfg.get('style_preset', 'cinematic') }}.
- Emission mode: {{ image_cfg.get('emit_mode', 'key_moments') }}.
- Multi-scene policy: {{ image_cfg.get('multi_scene_policy', 'comic') }}.
- Reference frame count target: {{ image_cfg.get('reference_count', 2) }}.
- Strict continuity: {{ image_cfg.get('strict_continuity', true) }}.
- If this turn is character creation and includes `json:character_sheet`, skip `json:story_image`.
- When narrative spans multiple scenes/parallel beats, prefer `scene_frames` and set `layout_preference` to `comic`.

{% if image_cfg.get('emit_mode', 'key_moments') == 'every_turn' %}
Mandatory policy:
- For every narration response (except character creation), append one `json:story_image` block.
{% else %}
Policy for key moments:
- Emit `json:story_image` at major reveals, scene transitions, combat beats, or emotional close-ups.
- If there is no prior story image yet, prefer emitting one in the current or next narrative turn.
{% endif %}

{% if story_images %}
Recent image references (newest last):
{% for image in story_images %}
- id={{ image.image_id }} | title={{ image.title }} | prompt={{ image.prompt }}
{% endfor %}
{% else %}
No previous image exists yet; if this is a meaningful scene, output an initial `json:story_image` now.
{% endif %}
