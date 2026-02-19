---
name: inventory
version: 2.0.0
description: 物品获取、使用、装备管理系统。
when_to_use:
  - 角色获得或失去物品时
  - 战斗/探索后发现战利品时
  - 角色使用消耗品或装备/卸下装备时
  - 需要展示物品效果时
avoid_when:
  - 纯叙事对话无物品交互
  - 物品仅在描述中提及但未实际获取
capability_summary: |
  提供物品管理能力。可输出 json:item_update 记录物品变动，
  json:loot 展示战利品，或通过 json:plugin_use 调用
  inventory.use_item 计算消耗品效果。
---

# Purpose
管理角色的物品与装备，追踪物品获取、使用和装备状态。

# Capabilities
- inventory.use_item: 使用消耗品，计算效果（如恢复生命值），返回结构化结果

# Direct Blocks

## json:item_update
当角色获得、失去、使用、装备或卸下物品时输出：

```json:item_update
{"action": "gain", "item_name": "生命药水", "quantity": 2, "item_type": "consumable", "description": "恢复20点生命值的红色药水", "stats": {"hp": 20}}
```

必需字段：action, item_name, quantity, item_type。
可选字段：description, stats。

action 取值：gain（获得）、lose（失去）、use（使用）、equip（装备）、unequip（卸下）。
item_type 取值：weapon（武器）、armor（护甲）、consumable（消耗品）、quest（任务物品）、misc（杂物）。

## json:loot
战斗或探索后发现物品时输出：

```json:loot
{"source": "哥布林营地宝箱", "items": [{"name": "铁剑", "type": "weapon", "quantity": 1, "rarity": "uncommon", "description": "一把坚固的铁剑"}], "gold": 50}
```

必需字段：source, items。可选字段：gold。
rarity 取值：common（普通）、uncommon（优秀）、rare（稀有）、epic（史诗）、legendary（传说）。

# Rules
- 每次物品变动独立输出一个 item_update block
- 战利品统一用一个 loot block 展示
- 消耗品使用建议通过 plugin_use 调用 inventory.use_item 以确保效果计算正确
- 不要凭空给予过多物品，遵循 loot_frequency 设置
