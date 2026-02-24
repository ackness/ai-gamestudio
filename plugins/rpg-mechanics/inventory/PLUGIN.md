---
name: inventory
description: 物品获取、使用、装备与战利品管理系统。
when_to_use:
  - 角色获得或失去物品时
  - 战斗/探索后发现战利品时
  - 角色使用消耗品或装备/卸下装备时
avoid_when:
  - 纯叙事对话无物品交互
capability_summary: |
  合并自 inventory + loot。提供 json:item_update 和 json:loot block，
  以及 inventory.use_item 能力。
---

## Inventory Plugin

Merged from: inventory + loot

### Item Management (json:item_update)
角色获得、失去、使用、装备或卸下物品时输出。

### Loot (json:loot)
战斗或探索后发现物品时输出。

### Capabilities
- inventory.use_item: 使用消耗品，计算效果并返回结果。
