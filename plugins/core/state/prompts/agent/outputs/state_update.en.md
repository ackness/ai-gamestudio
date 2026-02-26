Call `emit` when character or world state truly changed this turn.

State writes:
- Persist character/world deltas through `writes`.

Output shape:
- Add `{ "type": "state_update", "data": {...} }` into `items`.
- `data` must contain only this-turn deltas and include at least one of `characters` or `world`.

Character constraints:
- For existing characters, prefer the real `character_id` from context (`[id: ...]`).
- Do not use aliases like `player` or `npc_xxx` as `character_id`.
- If `character_id` is missing, provide at least `name` (preferably with `role`).
- Put extended character state under `attributes`; do not add custom root keys under `state_update`.

World bootstrap:
- When the first stable scene anchor appears, also set `world.current_scene` (at least `name`).
