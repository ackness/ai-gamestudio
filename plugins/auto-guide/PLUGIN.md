---
name: auto-guide
description: Optional action-suggestion block plugin rendered as quick actions after narration. When enabled, supersedes the choices plugin.
type: gameplay
required: false
version: "1.2"
extensions:
  runtime_settings:
    fields:
      category_count:
        type: integer
        label: Guide Categories
        description: Preferred number of guide categories per response.
        default: 3
        min: 2
        max: 4
        affects:
          - choices
      suggestion_style:
        type: enum
        label: Guide Suggestion Style
        description: Tone for suggested player actions.
        default: concise
        options:
          - concise
          - descriptive
          - tactical
        affects:
          - choices
      include_wild_category:
        type: boolean
        label: Include Wild Category
        description: Whether to encourage a wild option in most turns.
        default: true
        affects:
          - choices

blocks:
  guide:
    instruction: |
      在每次叙事回复的末尾，附加一个 json:guide 代码块为玩家提供行动建议。
      格式：
      ```json:guide
      {
        "categories": [
          {"style": "safe", "label": "稳妥的选择", "suggestions": ["行动描述"]},
          {"style": "aggressive", "label": "激进的选择", "suggestions": ["行动描述"]},
          {"style": "creative", "label": "另辟蹊径", "suggestions": ["行动描述"]},
          {"style": "wild", "label": "天马行空", "suggestions": ["行动描述"]}
        ]
      }
      ```
      如果本次回复已包含 json:character_sheet，则不要输出 json:guide。
    requires_response: false
    ui:
      component: custom
      renderer_name: guide

prompt:
  position: pre-response
  priority: 90
  template: prompts/guide-instruction.md
---

## Auto-Guide Plugin

Current runtime behavior:

- Frontend custom renderer displays `guide` categories and suggestions.
- Clicking a suggestion sends it as the next player action.
- When this plugin is enabled, it replaces the choices plugin's simpler format.
