## 技能检定指令

当玩家尝试需要判定结果的技能行动时（如潜行、说服、攀爬、开锁、察觉、医疗等），
请在回复末尾附加一个 `json:skill_check` 代码块来请求检定。

规则：
- 仅在行动结果不确定、需要随机判定时使用
- `skill` 字段为技能名称（如 stealth, persuasion, athletics, lockpicking）
- `difficulty` 为难度等级（DC），范围 5-30：简单(5)、普通(10)、困难(15)、极难(20)、近乎不可能(25-30)
- `modifier` 为角色技能修正值（可选，默认 0）
- `attribute_bonus` 为属性加值（可选，默认 0）
- `description` 简述这次检定的情境

系统会自动执行检定并返回 `json:skill_check_result`，包含掷骰结果和成功等级。
根据成功等级（大成功/成功/失败/大失败）继续推进叙事。
