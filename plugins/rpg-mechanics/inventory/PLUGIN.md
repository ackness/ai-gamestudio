---
name: inventory
description: 物品获取、使用、装备与战利品管理系统。
when_to_use:
  - 角色获得或失去物品时
  - 战斗/探索后发现战利品时
  - 角色使用消耗品或装备/卸下装备时
avoid_when:
  - 纯叙事对话无物品交互
---

## Inventory Plugin

Merged from: inventory + loot

### 工作流程
1. 阅读上下文中的角色物品栏数据（已提供，无需 db_read）
2. 用 update_and_emit 一次完成物品栏更新 + 前端通知

### 示例：获得物品
```
update_and_emit({
  "writes": [
    {"collection": "characters", "key": "角色名", "value": {"name": "...", "attributes": {...}, "inventory": ["长剑", "干粮", "新物品"]}}
  ],
  "emits": [
    {"type": "item_update", "data": {"action": "gain", "character": "角色名", "items": [{"name": "新物品", "quantity": 1}]}}
  ]
})
```

### Item Management (json:item_update)
角色获得、失去、使用、装备或卸下物品时输出。

### Loot (json:loot)
战斗或探索后发现物品时输出。先更新角色 inventory，再 emit loot block。

### Capabilities
- inventory.use_item: 使用消耗品，通过 execute_script 调用，计算效果并返回结果。
