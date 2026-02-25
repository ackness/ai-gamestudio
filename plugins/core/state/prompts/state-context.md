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
当需要创建角色时，调用 `emit`，在 `items` 中输出 `type=character_sheet`。
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

## 结构化输出规则（统一使用 emit）

叙事优先，仅在确有状态变化时调用 `emit`。

### state_update
必须在以下场景输出：
- 角色属性变化（战斗伤害、恢复、修炼等）
- 物品增减（拾取、使用、丢弃、交易）
- 货币变化
- 世界状态被玩家行动永久改变

要求：
- `items` 中加入 `type=state_update`
- `data` 只包含本回合增量
- `data` 至少包含 `characters` 或 `world` 之一

### notification
用于重要提醒、警告、奖励反馈。

要求：
- `items` 中加入 `type=notification`
- `data.content` 必填
- `data.level` 使用 `info` / `warning` / `success` / `error`

### scene_update
仅在玩家实际切换地点或当前场景被更新时输出。

要求：
- `items` 中加入 `type=scene_update`
- 当 `action=move` 时必须提供 `name`

### character_sheet
仅用于角色创建阶段。

要求：
- `items` 中加入 `type=character_sheet`
- `data.name` 必填
- 新建角色时使用 `character_id="new"`

{% if player %}
当前玩家角色「{{ player.name }}」已创建，本回合不要再输出 `character_sheet`。
{% endif %}

### NPC 管理
- 新建 NPC：在 `state_update.data.characters` 中追加 NPC 数据
- 更新 NPC：带上已有 `character_id`，只提交变化字段

{% set core_cfg = runtime_settings.get('state', {}) if runtime_settings else {} %}
{% if core_cfg %}
## 用户运行时设置（必须遵守）
- 叙事语气: {{ core_cfg.get('narrative_tone', 'neutral') }}
- 叙事节奏: {{ core_cfg.get('pacing', 'balanced') }}
- 回复长度: {{ core_cfg.get('response_length', 'medium') }}
- 风险倾向: {{ core_cfg.get('risk_bias', 'balanced') }}
{% endif %}
