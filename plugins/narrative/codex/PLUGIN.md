---
name: codex
description: 记录玩家发现的知识条目，包括怪物、物品、地点、传说与角色。
when_to_use:
  - 玩家首次遭遇新怪物或敌人
  - 玩家获得或发现新物品
  - 玩家到达新地点
  - 玩家了解到重要传说或历史
avoid_when:
  - 重复提及已完全记录的信息
  - 玩家未实际获得新知识
capability_summary: |
  从 codex 迁移。自动记录玩家发现的各类知识条目，
  按类别（怪物/物品/地点/传说/角色）分类管理。
---

## Codex Plugin

Migrated from: codex

Records discovered knowledge entries across categories (monster/item/location/lore/character).
Uses json:codex_entry blocks with unlock/update actions.
