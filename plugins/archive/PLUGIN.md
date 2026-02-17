---
name: archive
description: Required versioned-archive plugin. Summarizes long sessions and restores snapshots.
type: global
required: true
version: "1.1"
dependencies:
  - database
prompt:
  position: memory
  priority: 5
  template: prompts/archive-context.md
storage:
  keys:
    - config
    - session-meta
    - session-versions
---

## Archive Plugin

Current runtime behavior:

- Required plugin, always enabled.
- Initializes per-session archive metadata.
- Auto-summarizes every N turns (default 8) when enabled.
- Supports manual summarize and restore via archive APIs.
- Injects active archive summary into prompt memory section.
