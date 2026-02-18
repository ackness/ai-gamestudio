---
name: choices
version: 2.0.0
description: 可选交互式选项 block 插件，支持单选/多选。
when_to_use:
  - 玩家需要从选项中做出决策
  - 需要结构化的选项展示
avoid_when:
  - 开放式对话场景
  - auto-guide 插件已启用时
capability_summary: |
  提供 json:choices block 输出能力，支持单选和多选模式。
---

## Choices Plugin

Current runtime behavior:

- Frontend custom renderer handles `json:choices`.
- Single-choice click sends one message immediately.
- Multi-choice sends combined selection after confirmation.
