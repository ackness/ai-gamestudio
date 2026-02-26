Use `emit` as the only channel for structured guide output.

Prefer a single call with:
- `items`: one or more `guide`/`choices` blocks.

Example:
```json
{
  "items": [
    {
      "type": "guide",
      "data": {
        "categories": [
          {"style": "safe", "suggestions": ["Observe the enemy formation first."]}
        ]
      }
    }
  ]
}
```
