当需要向玩家展示提醒、警告或奖励信息时调用 `emit`。

输出结构：
- 在 `items` 中加入 `{ "type": "notification", "data": {...} }`。
- `data.content` 必填；`data.level` 使用 `info|warning|success|error`。
