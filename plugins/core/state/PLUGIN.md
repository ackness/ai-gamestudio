---
name: state
description: 核心状态管理：状态同步、角色卡、场景更新、通知与角色上下文注入。
when_to_use:
  - 任何涉及角色/世界/场景状态变化的回合
  - 需要角色/NPC/场景上下文时（始终启用）
  - 需要向玩家显示重要提示时
avoid_when:
  - 纯对话无状态变化
capability_summary: |
  提供 state_update / character_sheet / scene_update / notification
  四种基础 block 类型，以及角色上下文注入。是其他插件的基础依赖。
---

## State Plugin

Merged from: core-blocks (state_update, character_sheet, scene_update, notification) + character

### State Sync & Character Context

- Required plugin, always enabled.
- Injects player/NPC/scene context into the prompt.
- Defines baseline block types for state management.

### Block Types

- `json:state_update` — Sync character attributes, inventory, and world state changes.
- `json:character_sheet` — Create or edit character cards (creation phase only).
- `json:scene_update` — Track player movement between locations.
- `json:notification` — Player-facing alerts and system messages.
