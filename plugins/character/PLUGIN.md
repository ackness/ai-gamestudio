---
name: character
description: Character context injection plugin for player/NPC state and character-related output guidance.
type: gameplay
required: true
version: "1.1"
dependencies:
  - database
  - core-blocks
prompt:
  position: character
  priority: 10
  template: prompts/character-state.md
storage:
  keys:
    - characters
    - character-templates
    - inventories
---

## Character Plugin

Current runtime behavior:

- Required plugin, always enabled.
- Injects player/NPC/scene context into the prompt.
- Uses core block types for character operations:
  - `json:character_sheet` for create/edit workflow.
  - `json:state_update` for attribute/inventory/world sync.
- No standalone plugin hook scripts are executed by the backend.
