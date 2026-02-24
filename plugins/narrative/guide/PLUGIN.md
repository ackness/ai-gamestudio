---
name: guide
description: 行动建议与交互选项，引导玩家决策。
when_to_use:
  - 每次叙事回复后需要建议行动
  - 玩家需要从选项中做出决策
avoid_when:
  - 本次回复已包含 json:character_sheet
  - 系统消息或纯机械操作
---

## Guide Plugin

Merged from: auto-guide + choices

### Guide Mode (json:guide)
Categorized action suggestions (safe/aggressive/creative/wild) rendered as quick actions.

### Choices Mode (json:choices)
Simple single/multi selection for key decision points.

Use guide_mode setting to switch between modes.
