在角色或世界状态变化时，调用 `emit`。

写入状态：
- 使用 `writes` 持久化角色/世界变更。

输出结构：
- 在 `items` 中加入 `{ "type": "state_update", "data": {...} }`。
- `data` 只包含本回合真实增量，且至少包含 `characters` 或 `world`。

角色字段约束：
- 更新已有角色：优先使用上下文里的真实 `character_id`（`[id: ...]`）。
- 禁止使用 `player`、`npc_xxx` 等别名作为 `character_id`。
- 若没有 `character_id`，至少给出 `name`（建议附带 `role`）。
- 角色扩展状态放入 `attributes`，不要在 `state_update` 根对象新增自定义键。

世界初始化约束：
- 首次建立稳定场景时，同时输出 `world.current_scene`（至少 `name`）。

示例：
`{"type":"state_update","data":{"characters":[{"character_id":"<real_character_id>","attributes":{"hp":92,"focus":"stable"}}],"world":{"current_scene":{"name":"Whisperwind Inn","description":"Rainy night"}}}}`
