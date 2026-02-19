## 当前活跃任务

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
