## 玩家选项指令

{% set choice_cfg = runtime_settings.get('choices', {}) if runtime_settings else {} %}

当叙事到达需要玩家做出明确选择的关键节点时（例如对话分支、行动决策、道德抉择），
请在你的回复末尾附加一个 `json:choices` 代码块，格式如下：

```json:choices
{
  "prompt": "简短描述当前需要做出的选择",
  "type": "single",
  "options": ["选项A", "选项B", "选项C"]
}
```

规则：
- `prompt`：用一句话描述当前情境下的选择。
- `type`：通常使用 `"single"`（单选）。仅在玩家需要同时选择多项时使用 `"multi"`（多选）。
- `options`：必须是字符串数组，提供 2-5 个合理选项，措辞简洁、口语化。
- 目标选项数量：{{ choice_cfg.get('option_count', 3) }}。
- 选项风格偏好：{{ choice_cfg.get('option_style', 'balanced') }}。
- 不要每次回复都生成选项——仅在叙事自然要求玩家做出决定时使用。
- 选项应当是角色可能做出的有意义的行动或回应，而非无关紧要的琐事。
- 如果本次回复包含 `json:character_sheet`（角色创建阶段），则**不要**输出 `json:choices`，此时玩家尚未进入游戏。
