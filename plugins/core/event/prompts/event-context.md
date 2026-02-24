## 事件与任务追踪

### json:event — 事件追踪

**必须触发的场景：**
- `create`：玩家接受任务、发现线索、触发剧情事件、遭遇突发状况时
- `evolve`：任务有重大进展（找到关键线索、完成子目标、局势变化）时，需提供 event_id
- `resolve`：任务成功完成、谜题解开、目标达成时，需提供 event_id
- `end`：任务失败、被放弃、条件永久丧失时，需提供 event_id

**重要：** 积极管理事件生命周期。每个 create 的事件最终都应该 resolve 或 end。不要让事件永远停留在 active。当叙事推进到事件结局时，务必输出对应的 resolve/end block。

### json:quest_update — 任务管理

{% if storage and storage['active-quests'] %}
以下是玩家当前的活跃任务，请在叙事中考虑这些任务的进展：

{{ storage['active-quests'] | tojson }}

规则：
- 当玩家的行动推进了某个任务目标时，输出 json:quest_update 更新进度
- 当所有目标完成时，输出 action: "complete" 的 quest_update
- 根据叙事需要自然地引入新任务
- 任务复杂度：{{ settings.quest_complexity | default('standard') }}
- 奖励显示：{{ settings.show_rewards | default('preview') }}
{% else %}
当前没有活跃任务。根据叙事发展，可以通过 json:quest_update 创建新任务。
{% endif %}
