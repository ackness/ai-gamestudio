## 物品与装备指令

当叙事中涉及物品变动时（获得、失去、使用、装备、卸下），
请在回复末尾附加相应的 block。

### 物品变动 — json:item_update
角色获得、失去、使用、装备或卸下物品时输出：
```json:item_update
{"action": "gain", "item_name": "生命药水", "quantity": 1, "item_type": "consumable", "description": "恢复生命值的红色药水", "stats": {"hp": 20}}
```

规则：
- action 取值：gain / lose / use / equip / unequip
- item_type 取值：weapon / armor / consumable / quest / misc
- stats 可选，用于有属性效果的物品（如 {"hp": 20, "attack": 3}）
- 每次物品变动独立输出一个 block

### 战利品 — json:loot
战斗或探索后发现物品时输出：
```json:loot
{"source": "宝箱", "items": [{"name": "铁剑", "type": "weapon", "quantity": 1, "rarity": "uncommon", "description": "坚固的铁剑"}], "gold": 50}
```

规则：
- rarity 取值：common / uncommon / rare / epic / legendary
- gold 可选
- 不要每次回复都给战利品，遵循掉落频率设置
