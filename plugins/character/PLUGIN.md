---
name: character
version: 2.0.0
description: 角色上下文注入插件，负责玩家/NPC 状态和角色相关输出指导。
when_to_use:
  - 需要角色/NPC/场景上下文时（始终启用）
avoid_when: []
---

## Character Plugin

Current runtime behavior:

- Required plugin, always enabled.
- Injects player/NPC/scene context into the prompt.
- Uses core block types for character operations:
  - `json:character_sheet` for create/edit workflow.
  - `json:state_update` for attribute/inventory/world sync.
- No standalone plugin hook scripts are executed by the backend.
