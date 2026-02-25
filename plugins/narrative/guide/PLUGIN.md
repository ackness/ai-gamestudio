---
name: guide
description: 行动建议与交互选项，引导玩家决策。
when_to_use:
  - 每次叙事回复后需要建议行动
  - 玩家需要从选项中做出决策
avoid_when:
  - 本次回复正在创建角色
  - 系统消息或纯机械操作
---

## Guide Plugin

提供行动建议（guide）与明确选择（choices）。

### 工作流程
- 根据 `guide_mode` 决定输出类型：
  - `guide`：分类建议
  - `choices`：明确选项
- 使用 `emit.items` 输出对应结构。

### 示例
```json
{
  "items": [
    {
      "type": "choices",
      "data": {
        "prompt": "你要先做什么？",
        "type": "single",
        "options": ["先调查港口", "回酒馆打听消息", "直接去城北"]
      }
    }
  ]
}
```

### 规则
- 建议应可立即执行，避免空泛描述。
- 不在角色创建回合输出 guide/choices。
