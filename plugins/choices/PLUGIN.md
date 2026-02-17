---
name: choices
description: Optional interactive choice block plugin for single/multi selection.
type: gameplay
required: false
version: "1.1"
extensions:
  runtime_settings:
    fields:
      option_count:
        type: integer
        label: Choice Count
        description: Preferred number of options in json:choices.
        default: 3
        min: 2
        max: 5
        affects:
          - choices
      option_style:
        type: enum
        label: Choice Style
        description: Bias style for presented choices.
        default: balanced
        options:
          - conservative
          - balanced
          - bold
        affects:
          - choices

blocks:
  choices:
    instruction: |
      When the player must choose:
      ```json:choices
      {"prompt": "你要做什么？", "type": "single", "options": ["选项A", "选项B", "选项C"]}
      ```
      `options` must be an array of strings.
    requires_response: true
    ui:
      component: custom
      renderer_name: choices

prompt:
  position: pre-response
  priority: 80
  template: prompts/choices-instruction.md
---

## Choices Plugin

Current runtime behavior:

- Frontend custom renderer handles `json:choices`.
- Single-choice click sends one message immediately.
- Multi-choice sends combined selection after confirmation.
