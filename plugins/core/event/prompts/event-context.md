## 事件与任务追踪（统一使用 emit）

{% set storage = storage | default({}, true) %}
{% set runtime_settings = runtime_settings | default({}, true) %}

### event
在以下场景通过 `emit.items` 输出 `type=event`：
- `create`：接受任务、触发剧情、发现关键线索
- `evolve`：任务或事件出现重大推进
- `resolve`：事件成功收束
- `end`：事件失败或被放弃

要求：
- `evolve/resolve/end` 必须关联已有事件标识
- 每个 `create` 的事件最终都应 `resolve` 或 `end`

### quest_update
根据任务推进通过 `emit.items` 输出 `type=quest_update`。

{% if storage and storage['active-quests'] %}
当前活跃任务：
{{ storage['active-quests'] | tojson }}

执行规则：
- 玩家推进目标时输出 `quest_update`
- 目标全部完成时输出 `action=complete`
- 按叙事自然引入新任务
- 任务复杂度：{{ runtime_settings.get('quest_complexity', 'standard') }}
- 奖励显示：{{ runtime_settings.get('show_rewards', 'preview') }}
{% else %}
当前没有活跃任务。可按叙事需要创建新任务并输出 `quest_update`。
{% endif %}
