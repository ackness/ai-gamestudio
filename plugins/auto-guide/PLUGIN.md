---
name: auto-guide
version: 2.0.0
description: 可选行动建议 block 插件，叙事后以快速操作形式渲染。启用时取代 choices 插件。
when_to_use:
  - 每次叙事回复后需要建议行动
  - 玩家需要灵感或方向
avoid_when:
  - 本次回复已包含 json:character_sheet
  - 系统消息或纯机械操作
capability_summary: |
  提供 json:guide block 输出能力，按类别（稳妥/激进/创意/天马行空）
  组织行动建议。
---

## Auto-Guide Plugin

Current runtime behavior:

- Frontend custom renderer displays `guide` categories and suggestions.
- Clicking a suggestion sends it as the next player action.
- When this plugin is enabled, it replaces the choices plugin's simpler format.
