---
name: memory
description: 记忆、存档归档与自动压缩，管理长期上下文。
when_to_use:
  - 需要回忆之前发生的事件
  - 长期游戏需要保持一致性
  - 长期会话需要自动总结
  - 上下文窗口使用接近上限
avoid_when:
  - 短期测试游戏
  - 对话刚开始、轮次很少
---

## Memory Plugin

用于长期上下文维护，不向前端输出交互项。

### 工作流程
1. 阅读当前叙事与历史压缩摘要。
2. 通过 `emit` 的 `writes/logs` 持久化记忆数据。
3. 不在 `items` 中输出任何前端结构。

### 示例调用
```json
{
  "writes": [
    {"collection": "plugin.memory", "key": "memory_42", "value": {"id": "memory_42", "content": "玩家在港口获得线索", "timestamp": 42}},
    {"collection": "plugin.memory", "key": "memory_index", "value": {"count": 42, "latest": "memory_42"}}
  ],
  "logs": [
    {"collection": "memory_log", "entry": {"turn": 42, "reason": "quest-progress"}}
  ]
}
```

### 规则
- 仅记录关键信息：事件、人物关系、地点变化、未完线索。
- 无重要新增信息时可跳过写入。
