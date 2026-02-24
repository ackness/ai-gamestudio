---
name: auto-compress
version: 1.0.0
description: 当对话接近上下文窗口上限时，自动将旧对话压缩为叙事摘要，与记忆插件协同工作。
when_to_use:
  - 长期游戏对话轮次较多时
  - 上下文窗口使用接近上限
  - 需要保持叙事连贯性同时减少 token 消耗
avoid_when:
  - 对话刚开始、轮次很少
  - 手动管理记忆内容
---

## Auto-Compress Plugin

Automatically compresses old conversation history into narrative summaries when the context window usage approaches the configured threshold.

### How It Works

1. **Context monitoring:** Before each LLM call, the system estimates current context usage (prompt tokens / model max tokens).
2. **Threshold trigger:** When usage exceeds the `compression_threshold` setting (default 0.7), compression activates.
3. **LLM summarization:** Older messages (beyond the `keep_recent_messages` window) are sent to the LLM with a summarization prompt, producing a concise narrative summary.
4. **Summary storage:** The compressed summary is stored in `PluginStorage` under the `compression-summary` key and injected into future prompts at the `memory` position.
5. **Message pruning:** Compressed messages are excluded from subsequent prompt assembly, freeing context budget.

### Relationship with Memory Plugin

- **Memory plugin:** Captures specific events, character details, and world facts as discrete memory entries.
- **Auto-compress plugin:** Produces a background narrative summary of the overall conversation arc.
- Both inject at the `memory` prompt position. Auto-compress uses priority 5 (higher than memory's priority 10) so the compressed summary appears first, providing broad context before specific memories.

### Runtime Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `compression_threshold` | number | 0.7 | Context usage ratio that triggers compression (0.3 - 0.95) |
| `keep_recent_messages` | integer | 6 | Number of recent messages preserved after compression (2 - 20) |

### Storage Keys

- `compression-summary` — The latest compressed narrative summary text.
- `compression-state` — Metadata tracking compression state (last compressed message ID, timestamp, token counts).
