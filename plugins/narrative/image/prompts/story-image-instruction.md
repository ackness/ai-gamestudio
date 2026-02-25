## Story Image Guidance

{% set image_cfg = runtime_settings.get('image', {}) if runtime_settings else {} %}

{% if image_cfg.get('emit_mode', 'manual') == 'manual' %}
当前为手动模式：不要主动输出 `story_image`。
{% else %}
当画面值得可视化时，调用 `emit`，在 `items` 中输出 `type=story_image`。

要求：
- 必填字段：`story_background`、`prompt`
- `prompt` 只描述当前画面
- 如需连续性，补充 `reference_image_ids`
- 风格预设：{{ image_cfg.get('style_preset', 'cinematic') }}
- 触发模式：{{ image_cfg.get('emit_mode', 'key_moments') }}
- 多场景策略：{{ image_cfg.get('multi_scene_policy', 'comic') }}
- 参考帧数量：{{ image_cfg.get('reference_count', 2) }}
- 严格连续性：{{ image_cfg.get('strict_continuity', true) }}

{% if image_cfg.get('emit_mode', 'manual') == 'every_turn' %}
每个叙事回合都应输出一次 `story_image`（角色创建回合除外）。
{% else %}
优先在关键揭示、场景切换、战斗高潮、情绪特写时输出。
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
