当需要给玩家行动建议时，调用 `emit` 输出 `guide`。

要求：
- 在 `items` 中加入 `{ "type": "guide", "data": {...} }`。
- `data.categories` 为数组，每个分类至少包含 `style` 与 `suggestions`。
- 每条建议都要可立即执行，避免空泛描述。
