---
name: story-image
version: 2.0.0
description: 可选故事图像插件，将结构化提示转化为具有连续性的生成图像。
when_to_use:
  - 玩家手动点击"生成图片"按钮时（默认 manual 模式）
  - 关键叙事时刻需要视觉化（需将 emit_mode 切换为 key_moments）
  - 场景转换或高潮时刻
avoid_when:
  - 默认模式下 LLM 不应自动生成图片
  - 每个回合都生成（除非 emit_mode 设为 every_turn）
  - 纯对话无视觉需要
capability_summary: |
  提供 json:story_image block 输出能力，后端自动调用图像生成 API
  并返回带有连续性参考的图像。
---

## Story Image Plugin

Current runtime behavior:

- Backend calls image generation API and enriches `json:story_image`.
- Generated image metadata is persisted in plugin storage.
- Frontend custom renderer shows the image and supports regeneration.
