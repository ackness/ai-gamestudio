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

用于统一管理物品变更与战利品信息。

### 工作流程
1. 从上下文读取当前物品状态。
2. 调用 `emit.items` 输出 `item_update` 或 `loot`。
3. 需要计算物品效果时可调用 `inventory.use_item`。

### 示例
```json
{
  "items": [
    {"type": "item_update", "data": {"action": "gain", "item_name": "生命药水", "quantity": 1, "item_type": "consumable"}},
    {"type": "loot", "data": {"source": "山贼营地", "items": [{"name": "铁剑", "type": "weapon", "quantity": 1, "rarity": "uncommon"}]}}
  ]
}
```
