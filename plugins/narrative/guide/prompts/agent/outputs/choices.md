当需要玩家做明确选择时，调用 `emit` 输出 `choices`。

要求：
- 在 `items` 中加入 `{ "type": "choices", "data": {...} }`。
- `data` 必须包含 `prompt`、`type`（`single/multi`）和 `options`。
- `options` 中一个元素就是一个选项，不要把多个选项拼成一条。
- `options` 使用纯文本，不要使用 markdown。
