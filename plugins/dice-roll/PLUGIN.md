---
name: dice-roll
description: Optional dice-result block plugin with storage write and event emission.
type: gameplay
required: false
version: "1.1"

blocks:
  dice_result:
    instruction: |
      当需要随机判定时，在回复末尾输出：
      ```json:dice_result
      {"dice": "2d6+3", "result": 11, "success": true, "description": "命中！造成 11 点伤害"}
      ```
    schema:
      type: object
      properties:
        dice:
          type: string
        result:
          type: integer
        success:
          type: boolean
        description:
          type: string
      required:
        - dice
        - result
    handler:
      actions:
        - type: storage_write
          key: last-roll
        - type: emit_event
          event: dice-rolled
    ui:
      component: card
      title: "🎲 {{ dice }}"
      sections:
        - type: key-value
          items:
            - label: "结果"
              value: "{{ result }}"
            - label: "成功"
              value: "{{ success }}"
            - label: "描述"
              value: "{{ description }}"
      style:
        variant: info
    requires_response: false

events:
  emit:
    - dice-rolled

prompt:
  position: pre-response
  priority: 70
  template: prompts/dice-instruction.md
---

## Dice Roll Plugin

Current runtime behavior:

- `dice_result` is rendered by generic schema UI.
- Handler stores last roll in plugin storage and emits `dice-rolled` to request-scoped event bus.
