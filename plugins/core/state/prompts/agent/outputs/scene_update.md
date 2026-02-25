当地点切换或场景信息变化时调用 `emit`。

写入状态：
- 使用 `writes` 更新当前场景与关联信息。

输出结构：
- 在 `items` 中加入 `{ "type": "scene_update", "data": {...} }`。
- 若 `action = "move"`，`data.name` 必须是非空字符串。
- 不要仅传 `to/from` 而缺少 `name`，否则会被判定为无效。
