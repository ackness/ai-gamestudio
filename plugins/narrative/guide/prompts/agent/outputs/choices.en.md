Call `emit` with `choices` when the player must make an explicit decision.

Requirements:
- Add `{ "type": "choices", "data": {...} }` in `items`.
- `data` must include `prompt`, `type` (`single/multi`), and `options`.
- Each entry in `options` must represent exactly one action.
- Keep `options` as plain text (no markdown formatting).
