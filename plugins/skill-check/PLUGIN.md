---
name: skill-check
version: 2.0.0
description: 技能检定系统：执行能力/技能检定并与难度等级比较。
when_to_use:
  - 玩家尝试需要判定的技能行动（潜行、说服、攀爬、开锁、察觉等）
  - 需要对抗难度等级（DC）的检定
  - 非战斗场景中的能力测试
avoid_when:
  - 纯叙事无需判定
  - 战斗中的攻击判定（使用 combat 插件）
  - 结果已经确定的行动
capability_summary: |
  提供技能检定能力。输出 json:skill_check 请求检定，
  系统通过 skill_check.resolve 执行 1d20 + 修正值 vs 难度等级，
  返回 json:skill_check_result 包含成功等级。
---

# Purpose
对玩家的技能行动进行标准化检定，基于 D20 系统判定成功与否。

# Capabilities
- skill_check.resolve: 执行技能检定（1d20 + modifier + attribute_bonus vs difficulty），返回结构化结果

# Direct Blocks

## json:skill_check
当玩家尝试需要技能检定的行动时，输出此 block 请求检定：

```json:skill_check
{"skill": "stealth", "difficulty": 15, "modifier": 3, "attribute_bonus": 2, "description": "尝试潜行通过守卫"}
```

必需字段：skill, difficulty。可选字段：modifier, attribute_bonus, description。

## json:skill_check_result
由系统自动生成，包含检定结果：

```json:skill_check_result
{"dice": "1d20", "roll": 14, "modifier": 3, "attribute_bonus": 2, "total": 19, "difficulty": 15, "success_level": "success", "skill": "stealth", "description": "潜行检定：掷出 14 + 3 + 2 = 19 vs DC 15，成功！"}
```

# Rules
- 每次技能行动独立输出一个 skill_check block
- difficulty 通常在 5（简单）到 30（近乎不可能）之间
- 不要在无需判定的纯叙事中使用
- 大幅影响剧情的检定建议使用 plugin_use 调用 skill_check.resolve 以确保公正
- 成功等级：critical_success（自然20）、success（总值 >= DC）、failure（总值 < DC）、critical_failure（自然1）
