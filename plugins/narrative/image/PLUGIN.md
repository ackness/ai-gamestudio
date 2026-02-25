---
name: image
description: 将结构化提示词转换为保持连续性的生成图像。
when_to_use:
  - 玩家手动点击“生成图片”按钮时
  - 关键叙事时刻需要视觉化
avoid_when:
  - 手动模式下自动触发
  - 纯对话无视觉需求
---

## Image Plugin

根据叙事上下文生成图像请求数据，并由后端执行图像生成。

### 工作流程
- 当触发策略允许时，使用 `emit.items` 输出 `story_image`。
- 后端处理生成流程并回填结果，前端渲染图片与重生成功能。

### story_image 数据要求
- 必填：`story_background`、`prompt`
- 可选：`continuity_notes`、`reference_image_ids`、`scene_frames`、`layout_preference`
- `prompt` 只描述当前画面，不混入过多历史叙事
