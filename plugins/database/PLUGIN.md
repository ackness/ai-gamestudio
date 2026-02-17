---
name: database
description: Provides persistent state context for prompts and is required for all game sessions.
type: global
required: true
version: "1.1"
storage:
  keys:
    - world-state
    - event-log
prompt:
  position: world-state
  priority: 100
  template: prompts/world-state.md
---

## Database Plugin

Current runtime behavior:

- Required plugin, always enabled.
- Does not execute hook scripts.
- Provides world/state context through prompt injection.
- Persistent plugin data is stored in `PluginStorage` by plugin name + key.
