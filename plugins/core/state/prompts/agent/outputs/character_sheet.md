仅在玩家角色初始化或重建时调用 `emit` 输出角色卡数据。

强约束：
- `items` 必须包含且仅包含一个 `character_sheet`（角色创建场景）。
- `character_sheet.data` 必须是对象，`data.name` 必须是非空字符串。
- 创建新角色时必须使用 `data.character_id = "new"`。
- `data.editable_fields` 必须是数组，且必须包含 `"name"`。

写入状态：
- 可在 `writes` 中同步角色主数据。

标准结构示例：
```json
{
  "items": [
    {
      "type": "character_sheet",
      "data": {
        "character_id": "new",
        "name": "未命名冒险者",
        "role": "player",
        "editable_fields": ["name"],
        "attributes": {},
        "inventory": []
      }
    }
  ]
}
```
