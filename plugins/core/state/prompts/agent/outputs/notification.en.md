Call `emit` when you need to show reminders, warnings, or reward feedback to the player.

Output shape:
- Add `{ "type": "notification", "data": {...} }` into `items`.
- `data.content` is required.
- `data.level` must be one of `info|warning|success|error`.
