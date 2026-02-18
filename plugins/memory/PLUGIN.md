---
name: memory
version: 2.0.0
description: 可选记忆上下文注入插件，读取存储的记忆并注入到 prompt memory 位置。
when_to_use:
  - 需要回忆之前发生的事件
  - 长期游戏需要保持一致性
avoid_when:
  - 短期测试游戏
---

## Memory Plugin

Current runtime behavior:

- Optional plugin, can be toggled.
- Injects `memories` context into prompts when memory data exists.
- Backend does not execute plugin hook scripts for automatic extraction.
- Memory data is read from `PluginStorage` keys and used as plain prompt context.
