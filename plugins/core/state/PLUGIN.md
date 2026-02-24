---
name: state
description: 核心状态管理：状态同步、角色卡、场景更新、通知与角色上下文注入。
when_to_use:
  - 任何涉及角色/世界/场景状态变化的回合
  - 需要角色/NPC/场景上下文时（始终启用）
  - 需要向玩家显示重要提示时
avoid_when:
  - 纯对话无状态变化且无场景移动
---

## State Plugin

核心状态管理插件，始终启用。负责角色状态同步、角色卡创建、场景追踪和玩家通知。

### 工作流程
1. 阅读上下文中的游戏状态（已提供，无需 db_read）
2. 用 update_and_emit 一次完成 DB 写入 + 前端通知

### 示例调用
```
update_and_emit({
  "writes": [
    {"collection": "characters", "key": "角色名", "value": {name, attributes, inventory}}
  ],
  "emit": {"type": "state_update", "data": {"characters": [...], "world": {...}}}
})
```

### Block Types

#### state_update
当角色属性/HP/MP 变化、物品获得/失去/使用、金钱变化、技能习得时触发。

emit data 格式：
```json
{
  "characters": [
    {
      "name": "角色名",
      "attributes": {"气血": 90, "内力": 50},
      "inventory": ["长剑", "干粮"]
    }
  ],
  "world": {"key": "value"}
}
```
- 必须包含 `characters` 或 `world` 至少一个
- characters 数组中每个对象必须有 `name`
- 只包含实际变化的字段

#### character_sheet
仅在角色创建阶段触发。必须包含完整的角色信息。

emit data 格式：
```json
{
  "character_id": "new",
  "name": "角色名",
  "role": "武者",
  "description": "一名年轻的江湖游侠，身着青衫，腰佩长剑。",
  "background": "出身没落武林世家，自幼习武。",
  "editable_fields": ["name"],
  "attributes": {"气血": 100, "内力": 50, "体力": 80},
  "inventory": ["长剑", "干粮", "银两×20"]
}
```
- **name 是必填字段**
- character_id: 新建角色用 "new"

#### scene_update
当玩家移动到新地点或当前场景发生变化时触发。

emit data 格式：
```json
{
  "action": "move",
  "name": "新地点名",
  "description": "地点的详细描述",
  "npcs": [
    {"character_id": "npc_id", "name": "NPC名", "role_in_scene": "掌柜"}
  ]
}
```
- action 为 "move" 时，**name 是必填字段**

#### notification
向玩家显示重要提示信息。

emit data 格式：
```json
{"level": "info", "title": "提示", "content": "消息内容"}
```
- level: info / warning / success / danger

### Rules
- 每个回合只处理叙事中实际发生的变化
- 不要在没有状态变化时强行输出 state_update
- character_sheet 仅在角色创建阶段使用，已有玩家角色后不再触发
