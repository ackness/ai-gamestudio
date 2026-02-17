---
name: story-image
description: Optional story image plugin that converts structured prompts into generated images with continuity.
type: gameplay
required: false
version: "1.0"
dependencies:
  - core-blocks
  - database
extensions:
  runtime_settings:
    fields:
      style_preset:
        type: enum
        label: Image Style Preset
        description: Visual style direction for generated images.
        default: cinematic
        options:
          - cinematic
          - anime
          - oil-painting
          - photoreal
        affects:
          - image
      emit_mode:
        type: enum
        label: Image Emission Mode
        description: How frequently DM should emit story_image blocks.
        default: key_moments
        options:
          - key_moments
          - every_turn
        affects:
          - image
          - story
      multi_scene_policy:
        type: enum
        label: Multi-Scene Layout Policy
        description: Layout preference when prompt involves multiple scenes.
        default: comic
        options:
          - comic
          - auto
          - single
        affects:
          - image
      prompt_template:
        type: string
        label: Image Prompt Template
        description: |
          Use {{story_background}} and {{frame_prompt}} placeholders.
          Optional placeholders: {{continuity_notes}}, {{reference_summary}}, {{style_preset}}, {{negative_prompt}}.
        component: textarea
        scope: both
        default: |
          Style preset: {{style_preset}}
          Story background: {{story_background}}
          Current frame: {{frame_prompt}}
          Continuity notes: {{continuity_notes}}
          Reference summary:
          {{reference_summary}}
        affects:
          - image
      negative_prompt:
        type: string
        label: Negative Prompt
        description: Things to avoid in generated images.
        component: textarea
        default: blurry, extra limbs, distorted face, low detail
        affects:
          - image
      reference_count:
        type: integer
        label: Reference Frames Count
        description: Max previous frames used as reference.
        default: 2
        min: 0
        max: 6
        affects:
          - image
      strict_continuity:
        type: boolean
        label: Strict Continuity
        description: Keep stronger character/prop consistency.
        default: true
        affects:
          - image

blocks:
  story_image:
    instruction: |
      When the current moment should be visualized, append:
      ```json:story_image
      {
        "title": "Scene cover title",
        "story_background": "What happened before this frame, in 1-3 sentences.",
        "prompt": "What should be shown in this exact frame.",
        "continuity_notes": "Visual continuity constraints.",
        "reference_image_ids": ["optional-previous-image-id"],
        "layout_preference": "auto",
        "scene_frames": ["optional scene beat 1", "optional scene beat 2"]
      }
      ```
      Rules:
      - `story_background` is required for every image.
      - `prompt` must describe only the current frame.
      - For follow-up frames, always include `reference_image_ids` from prior `story_image` blocks when available.
      - Prior image references are mainly for style/character continuity; scene can still change when story requires.
      - Do not emit `story_image` in every turn; use only key moments.
    schema:
      type: object
      properties:
        title:
          type: string
        story_background:
          type: string
        prompt:
          type: string
        continuity_notes:
          type: string
        reference_image_ids:
          type: array
          items:
            type: string
        layout_preference:
          type: string
        scene_frames:
          type: array
          items:
            type: string
      required:
        - story_background
        - prompt
    handler:
      actions:
        - type: builtin
          handler_name: story_image_builtin
    requires_response: true
    ui:
      component: custom
      renderer_name: story_image

prompt:
  position: pre-response
  priority: 92
  template: prompts/story-image-instruction.md
---

## Story Image Plugin

Current runtime behavior:

- Backend calls image generation API and enriches `json:story_image`.
- Generated image metadata is persisted in plugin storage.
- Frontend custom renderer shows the image and supports regeneration.
