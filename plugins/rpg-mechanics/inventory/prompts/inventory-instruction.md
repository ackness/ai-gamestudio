## 物品与装备指令（统一使用 emit）

当叙事涉及物品变动时，调用 `emit`，在 `items` 中输出对应类型。

### item_update
适用于获得、失去、使用、装备、卸下。

要求：
- action：gain / lose / use / equip / unequip
- 传递物品名、数量、类型
- 如存在属性效果，可附 `stats`

**重要：同步角色背包**
输出 `item_update` 后，必须在同一次 emit 中额外输出一个 `state_update`，将变动后的完整物品列表写入角色的 inventory 字段，否则角色面板不会更新。示例：
```json
{"items": [
  {"type": "item_update", "data": {"action": "gain", "item_name": "清心丹", "quantity": 1, "item_type": "consumable", "description": "能暂时压制内力异动的丹药"}},
  {"type": "state_update", "data": {"characters": [{"character_id": "<玩家角色ID>", "inventory": ["铁剑", "碎银", "一封信", "清心丹"]}]}}
]}
```
- `inventory` 数组应包含变动后的全部物品（不是增量，是全量）
- 从上下文中读取当前角色的 inventory，合并变动后输出

### loot
适用于战斗或探索后的战利品结算。

要求：
- 给出来源、物品列表
- 可附金币
- 遵循掉落频率设置，不要每回合都输出
- 同样需要附带 `state_update` 同步角色背包（规则同 item_update）
