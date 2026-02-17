## Character Context

{% if player %}
### Player
- Name: {{ player.name }} [id: {{ player.id }}]
{% if player.description %}- Description: {{ player.description }}{% endif %}
{% if player.attributes %}
- Attributes: {{ player.attributes }}
{% endif %}
{% if player.inventory %}
- Inventory: {{ player.inventory }}
{% endif %}
{% else %}
### Player
No player character exists yet.
When character creation is needed, output a `json:character_sheet` block.
{% endif %}

{% if npcs %}
### NPCs
{% for npc in npcs %}
- {{ npc.name }} ({{ npc.role }}) [id: {{ npc.id }}]{% if npc.description %}: {{ npc.description }}{% endif %}
{% endfor %}
{% endif %}

{% if current_scene %}
### Scene
- {{ current_scene.name }}{% if current_scene.description %}: {{ current_scene.description }}{% endif %}
{% if scene_npcs %}
- NPCs in scene: {% for npc in scene_npcs %}{{ npc.name }}{% if npc.role_in_scene %}({{ npc.role_in_scene }}){% endif %}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}
{% endif %}

## Character Output Rules

### `json:character_sheet` — 仅用于角色创建

**只在游戏初始化、玩家尚未拥有角色时**输出 `json:character_sheet`。一旦角色创建完成（玩家已确认），后续回复中**绝对不要**再输出 `json:character_sheet`。

```json:character_sheet
{
  "character_id": "new",
  "name": "角色名",
  "role": "player",
  "description": "角色描述",
  "attributes": {
    "体力": 100
  },
  "inventory": [],
  "editable_fields": ["name", "description"]
}
```

{% if player %}
**当前玩家角色「{{ player.name }}」已创建，不要再输出 `json:character_sheet`。**
{% endif %}

### `json:state_update` — 角色状态变更

当角色属性、物品等发生变化时，使用 `json:state_update`（而非 `character_sheet`）：

```json:state_update
{
  "characters": [
    {
      "character_id": "角色ID或省略以按名字新建",
      "name": "角色名",
      "attributes": {
        "体力": 90
      },
      "inventory": ["长剑", "治疗药水"]
    }
  ]
}
```

Only output `state_update` when the state truly changed.

### NPC 管理指引

作为 DM，你应积极管理 NPC 的生命周期：

- **新建 NPC**：当剧情中出现重要 NPC 时，通过 `json:state_update` 的 `characters` 数组创建（省略 `character_id`，提供 `name` 和 `role: "npc"`）。
- **更新 NPC**：当已有 NPC 的属性、状态或物品发生变化时，在 `characters` 数组中使用该 NPC 的 `character_id`（参见上方 NPCs 列表中的 id）进行更新。
- **部分更新**：只需包含变化的字段，未提及的属性会保留原值（attributes 会合并而非替换）。
- **批量操作**：可以在一次 `state_update` 中同时创建/更新多个角色。

示例 — 创建新 NPC：
```json:state_update
{
  "characters": [
    {
      "name": "神秘旅者",
      "role": "npc",
      "description": "身披灰色斗篷的陌生人",
      "personality": "沉默寡言，目光锐利",
      "attributes": { "威胁等级": "未知" }
    }
  ]
}
```

示例 — 更新已有 NPC（使用 id）：
```json:state_update
{
  "characters": [
    {
      "character_id": "已有角色的ID",
      "attributes": { "好感度": 60 },
      "inventory": ["密信"]
    }
  ]
}
```
