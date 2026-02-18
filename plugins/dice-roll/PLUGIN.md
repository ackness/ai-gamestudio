---
name: dice-roll
version: 2.0.0
description: 处理骰子检定与概率判定。
when_to_use:
  - 需要随机判定（攻击/防御/技能检定）
  - 需要命中/豁免计算
  - 概率事件需要公正裁决
avoid_when:
  - 纯叙事无检定
  - 已经有确定结果的行动
capability_summary: |
  提供骰子解析与执行能力。可直接输出 json:dice_result，
  或通过 json:plugin_use 调用 dice.roll capability 让后端掷骰。
---

# Purpose
对检定请求生成标准化随机结果。

# Capabilities
- dice.roll: 解析骰子表达式（如 2d6+3, 1d20）并输出结构化掷骰结果

# Direct Blocks

## json:dice_result
当需要随机判定时（攻击/防御/技能检定/概率事件），输出此 block：

```json:dice_result
{"dice": "2d6+3", "result": 11, "success": true, "description": "掷出 2d6+3 = 4+4+3 = 11"}
```

必需字段：dice, result。可选字段：success, description。

# Fallback
脚本失败时输出 json:notification，提示玩家手动判定。

# Rules
- 每个检定独立输出一个 dice_result block
- 不要在纯叙事中无故掷骰
- 重大判定建议使用 plugin_use 调用 dice.roll 以确保公正
