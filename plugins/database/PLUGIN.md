---
name: database
version: 2.0.0
description: 提供持久化状态上下文注入，是所有游戏会话的必需插件。
when_to_use:
  - 需要世界/状态上下文时（始终启用）
avoid_when: []
---

## Database Plugin

Current runtime behavior:

- Required plugin, always enabled.
- Does not execute hook scripts.
- Provides world/state context through prompt injection.
- Persistent plugin data is stored in `PluginStorage` by plugin name + key.
