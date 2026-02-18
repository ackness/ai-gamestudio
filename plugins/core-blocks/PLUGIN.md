---
name: core-blocks
version: 2.0.0
description: 核心 block 类型定义：状态同步、角色卡、场景、事件、通知。
when_to_use:
  - 任何涉及角色/世界/场景/事件状态变化的回合
  - 需要向玩家显示重要提示时
avoid_when:
  - 纯对话无状态变化
capability_summary: |
  提供 state_update / character_sheet / scene_update / event / notification
  五种基础 block 类型，是其他插件的基础依赖。
---

## Core Blocks Plugin

Defines the baseline block types consumed by the backend dispatcher and frontend renderers.
