---
name: image
description: 将结构化提示词转换为保持连续性的生成图像。
when_to_use:
  - 玩家手动点击"生成图片"按钮时
  - 关键叙事时刻需要视觉化
avoid_when:
  - 默认模式下 LLM 不应自动生成图片
  - 纯对话无视觉需要
---

## Image Plugin

Migrated from: story-image

- Backend calls image generation API and enriches `json:story_image`.
- Generated image metadata is persisted in plugin storage.
- Frontend custom renderer shows the image and supports regeneration.
