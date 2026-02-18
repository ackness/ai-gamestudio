---
name: archive
version: 2.0.0
description: 必需版本存档插件。自动总结长会话并支持快照恢复。
when_to_use:
  - 长期会话需要自动总结（始终启用）
avoid_when: []
---

## Archive Plugin

Current runtime behavior:

- Required plugin, always enabled.
- Initializes per-session archive metadata.
- Auto-summarizes every N turns (default 8) when enabled.
- Supports manual summarize and restore via archive APIs.
- Injects active archive summary into prompt memory section.
