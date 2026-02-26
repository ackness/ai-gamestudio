Call `emit` when location changes or current scene information changes.

State writes:
- Use `writes` to update current scene and related state.

Output shape:
- Add `{ "type": "scene_update", "data": {...} }` into `items`.
- If `action = "move"`, `data.name` must be a non-empty string.
- Do not send only `to/from` without `name`, or it will be rejected.
