---
name: image
description: 将结构化提示词转换为保持连续性的生成图像。
when_to_use:
  - 玩家手动点击"生成图片"按钮时
  - 关键叙事时刻需要视觉化
avoid_when:
  - 默认模式下 LLM 不应自动生成图片
  - 纯对话无视觉需要
capability_summary: |
  从 story-image 迁移。提供 json:story_image block，
  后端自动调用图像生成 API 并返回带有连续性参考的图像。
---

## Image Plugin

Migrated from: story-image

- Backend calls image generation API and enriches `json:story_image`.
- Generated image metadata is persisted in plugin storage.
- Frontend custom renderer shows the image and supports regeneration.
