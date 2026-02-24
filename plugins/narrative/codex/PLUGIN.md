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
---

## Codex Plugin

Migrated from: codex

Records discovered knowledge entries across categories (monster/item/location/lore/character).

### 工作流程
1. 阅读上下文中的 codex 数据（已提供，无需 db_read），避免重复
2. 用 update_and_emit 一次完成新条目存储 + 前端通知

### 示例：发现多个新条目
```
update_and_emit({
  "writes": [
    {"collection": "codex", "key": "location_village", "value": {"category": "location", "entry_id": "village", "title": "...", "content": "...", "tags": [...]}},
    {"collection": "codex", "key": "monster_goblin", "value": {"category": "monster", "entry_id": "goblin", "title": "...", "content": "...", "tags": [...]}}
  ],
  "emits": [
    {"type": "codex_entry", "data": {"action": "unlock", "category": "location", "entry_id": "village", "title": "...", "content": "...", "tags": [...]}},
    {"type": "codex_entry", "data": {"action": "unlock", "category": "monster", "entry_id": "goblin", "title": "...", "content": "...", "tags": [...]}}
  ]
})
```

### emit_block 格式
Uses json:codex_entry blocks with unlock/update actions.
action: unlock/update。category: monster/item/location/lore/character。
