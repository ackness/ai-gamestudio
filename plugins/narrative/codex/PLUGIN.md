---
name: codex
description: 记录玩家发现的知识条目，包括怪物、物品、地点、传说与角色。
when_to_use:
  - 玩家首次遭遇新怪物或敌人
  - 玩家获得或发现新物品
  - 玩家到达新地点
  - 玩家了解到重要传说或历史
avoid_when:
  - 重复提及已完全记录的信息
  - 玩家未实际获得新知识
---

## Codex Plugin

用于维护图鉴/百科条目，避免知识点丢失。

### 工作流程
1. 从上下文中读取现有条目，避免重复。
2. 用 `emit.items` 输出 `codex_entry`（unlock/update）。
3. 按需写入存储并触发后续事件。

### 示例
```json
{
  "items": [
    {
      "type": "codex_entry",
      "data": {
        "action": "unlock",
        "category": "monster",
        "entry_id": "goblin",
        "title": "哥布林",
        "content": "矮小且群居的绿皮生物",
        "tags": ["敌人", "低阶"]
      }
    }
  ]
}
```
