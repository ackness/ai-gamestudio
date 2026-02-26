Call `emit` with `guide` when player action suggestions are needed.

Requirements:
- Add `{ "type": "guide", "data": {...} }` in `items`.
- `data.categories` must be an array; each category should include at least `style` and `suggestions`.
- Every suggestion should be immediately actionable and concrete.
