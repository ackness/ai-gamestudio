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

### Memory Context
- Injects stored memories into prompts for narrative consistency.
- Memory data is read from PluginStorage and used as plain prompt context.

### Archive
- Auto-summarizes every N turns (default 8) when enabled.
- Supports manual summarize and restore via archive APIs.
- Injects active archive summary into prompt memory section.

### Auto-Compress
- Monitors context usage before each LLM call.
- When usage exceeds threshold (default 0.7), compresses older messages into narrative summary.
- Summary stored in PluginStorage and injected at memory position.
- Works alongside discrete memory entries: compressed summary provides broad context, memories provide specifics.
