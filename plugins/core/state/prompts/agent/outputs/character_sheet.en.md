Use `emit` for `character_sheet` only during player character initialization/rebuild.

Hard constraints:
- In character-creation turns, `items` must contain exactly one `character_sheet`.
- `character_sheet.data` must be an object and `data.name` must be a non-empty string.
- Use `data.character_id = "new"` when creating a new character.
- `data.editable_fields` must be an array and include `"name"`.

State writes:
- You may sync primary character data in `writes`.
