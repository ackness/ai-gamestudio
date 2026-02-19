---
name: codex
version: 2.0.0
description: 记录玩家发现的知识条目，包括怪物、物品、地点、传说与角色。
when_to_use:
  - 玩家首次遭遇新怪物或敌人
  - 玩家获得或发现新物品
  - 玩家到达新地点
  - 玩家了解到重要传说或历史
  - 玩家结识重要 NPC
  - 已有条目获得重要补充信息
avoid_when:
  - 重复提及已完全记录的信息
  - 无关紧要的背景细节
  - 玩家未实际获得新知识
capability_summary: |
  自动记录玩家在冒险中发现的各类知识条目，
  按类别（怪物/物品/地点/传说/角色）分类管理。
---

# Purpose
构建玩家的知识图鉴，记录冒险中发现的所有重要信息。

# Direct Blocks

## json:codex_entry
当玩家获得新知识时输出此 block：

### 解锁新条目
```json:codex_entry
{"action": "unlock", "category": "monster", "entry_id": "shadow-wolf", "title": "暗影狼", "content": "栖息于黑暗森林的魔化狼群，双眼泛着紫色光芒。弱点是光系魔法。", "tags": ["魔兽", "黑暗森林"]}
```

### 更新已有条目
```json:codex_entry
{"action": "update", "category": "monster", "entry_id": "shadow-wolf", "title": "暗影狼", "content": "发现暗影狼在满月时力量会增强三倍，且会召唤同伴。", "tags": ["魔兽", "黑暗森林", "满月"]}
```

必需字段：action, category, entry_id, title, content。
可选字段：tags, image_hint。

### 类别说明
- monster：怪物与敌人
- item：物品与装备
- location：地点与区域
- lore：传说与历史
- character：重要 NPC 与角色

# Rules
- 每个新发现独立输出一个 codex_entry block
- entry_id 使用英文小写加连字符（如 shadow-wolf）
- 同一 entry_id 的 update 会补充而非覆盖原有信息
- content 应包含玩家实际了解到的信息，不要透露玩家未知的内容
- 首次发现用 unlock，后续补充用 update
- tags 用于分类检索，建议 2-4 个标签
