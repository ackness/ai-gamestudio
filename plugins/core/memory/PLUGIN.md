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

Merged from: memory + archive + auto-compress

本插件是基础设施插件，**不输出任何 emit_block**。仅使用 DB 工具管理记忆数据。

### 工作流程
1. 阅读上下文中的游戏状态（已提供，无需 db_read）
2. 将当前叙事摘要存入 DB：
```
update_and_emit({
  "writes": [
    {"collection": "plugin.memory", "key": "memory_<N>", "value": {"id": "memory_<N>", "content": "摘要", "timestamp": N}},
    {"collection": "plugin.memory", "key": "memory_index", "value": {"count": N, "latest": "memory_<N>"}}
  ]
})
```
3. 如果叙事内容简单或无重要信息，可以跳过不存储

### 规则
- **禁止使用 emit_block**，本插件不向前端输出任何 block
- 记忆摘要应简洁，提取关键事件、人物、地点信息
- collection 统一使用 "plugin.memory"
