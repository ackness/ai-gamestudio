---
name: memory
description: Optional memory-context injection plugin that reads stored memories and injects them at prompt position `memory`.
type: global
required: false
version: "1.1"
dependencies:
  - database
prompt:
  position: memory
  priority: 10
  template: prompts/memory-context.md
storage:
  keys:
    - short-term-memory
    - long-term-memory
    - memory-index
---

## Memory Plugin

Current runtime behavior:

- Optional plugin, can be toggled.
- Injects `memories` context into prompts when memory data exists.
- Backend does not execute plugin hook scripts for automatic extraction.
- Memory data is read from `PluginStorage` keys and used as plain prompt context.
