Use `emit` as the single channel for this turn's DB writes and structured outputs.

Prefer one call to include:
1. `writes`: persist character/world/scene updates.
2. `logs`: append logs when needed.
3. `items`: emit structured blocks.

Minimal example:
```json
{
  "writes": [{"collection": "characters", "key": "hero", "value": {"name": "Ayla"}}],
  "items": [{"type": "notification", "data": {"level": "info", "content": "Character state updated."}}]
}
```
