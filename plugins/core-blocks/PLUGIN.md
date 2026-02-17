---
name: core-blocks
description: Core block declarations for state sync, character sheets, scenes, events, and notifications.
type: global
required: true
version: "1.1"
extensions:
  runtime_settings:
    fields:
      narrative_tone:
        type: enum
        label: Narrative Tone
        description: Preferred tone for DM narration.
        default: neutral
        options:
          - neutral
          - grim
          - heroic
          - whimsical
        affects:
          - story
      pacing:
        type: enum
        label: Narrative Pacing
        description: Controls how quickly scenes and events progress.
        default: balanced
        options:
          - slow
          - balanced
          - fast
        affects:
          - story
          - choices
      response_length:
        type: enum
        label: Narration Length
        description: Desired average response length.
        default: medium
        options:
          - short
          - medium
          - long
        affects:
          - story
      risk_bias:
        type: enum
        label: Story Risk Bias
        description: Whether events should trend safer or more dangerous.
        default: balanced
        options:
          - safe
          - balanced
          - dangerous
        affects:
          - story
          - choices

prompt:
  position: system
  priority: 95
  template: prompts/core-instruction.md

blocks:
  state_update:
    instruction: |
      When character attributes, inventory, or world data changes:
      ```json:state_update
      {"characters": [{"name": "角色名", "attributes": {"气血": 90}, "inventory": ["长剑"]}], "world": {"world_doc": "..." }}
      ```
    handler:
      actions:
        - type: builtin
          handler_name: state_update
    ui:
      component: none

  character_sheet:
    instruction: |
      When creating or editing a character card:
      ```json:character_sheet
      {"character_id": "new", "name": "待定", "editable_fields": ["name"], "attributes": {"气血": 100}, "inventory": ["长剑"]}
      ```
    handler:
      actions:
        - type: builtin
          handler_name: character_sheet
    ui:
      component: custom
      renderer_name: character_sheet

  scene_update:
    instruction: |
      When the player moves to a new location or the current scene changes:
      ```json:scene_update
      {"action": "move", "name": "新地点名", "description": "地点描述", "npcs": [{"character_id": "npc_id", "role_in_scene": "掌柜"}]}
      ```
    handler:
      actions:
        - type: builtin
          handler_name: scene_update
    ui:
      component: custom
      renderer_name: scene_update

  event:
    instruction: |
      When a significant event is created, evolved, resolved, or ended:
      ```json:event
      {"action": "create", "event_type": "quest", "name": "事件名", "description": "事件描述", "visibility": "known"}
      ```
      Actions: create, evolve (with event_id of parent), resolve (with event_id), end (with event_id).
    handler:
      actions:
        - type: builtin
          handler_name: event
    ui:
      component: none

  notification:
    instruction: |
      For player-facing alerts:
      ```json:notification
      {"level": "info", "title": "提示", "content": "消息内容"}
      ```
    ui:
      component: custom
      renderer_name: notification
---

## Core Blocks Plugin

Defines the baseline block types consumed by the backend dispatcher and frontend renderers.
