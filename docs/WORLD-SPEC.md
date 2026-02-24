# World Spec (Markdown Frontmatter)

世界文档（`world_doc`）是项目的叙事底盘。它既给主 LLM 提供长期设定，也可通过 frontmatter 指定默认启用插件。

## 1. 推荐结构

```md
---
name: 玄铁江湖
description: 门派纷争与秘境探索并存的武侠世界
genre: wuxia
tags: [江湖, 门派, 秘境]
language: zh
plugins: [state, event, memory, guide, combat, inventory, social, codex]
---

# 世界概述
...

## 核心规则
...

## 势力与门派
...

## 关键地点
...

## 禁忌与底线
...
```

## 2. Frontmatter 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 否 | 世界名称 |
| `description` | string | 否 | 世界简介 |
| `genre` | string | 否 | 风格标签 |
| `tags` | string[] | 否 | 检索标签 |
| `language` | string | 否 | `zh` / `en` |
| `plugins` | string[] | 否 | 项目默认启用插件 |

## 3. 插件建议

### 3.1 基础稳定组合

- `database`（required）
- `state`（required）
- `event`（required）
- `memory`（建议）

### 3.2 叙事增强

- `guide`
- `codex`
- `image`

### 3.3 机制增强

- `combat`
- `inventory`
- `social`

## 4. 编写建议

- 先写不可变设定：世界规则、时代背景、力量体系。
- 再写可演化设定：势力关系、主线冲突、阶段目标。
- 明确边界条件：禁用内容、叙事限制、风格底线。
- 保持条目化：便于模型检索与插件引用。

## 5. 示例：机制导向世界

```md
---
name: 铁潮边境
genre: steampunk
tags: [工业, 边境, 战争]
plugins: [state, event, memory, guide, combat, inventory]
---

# 基础设定
- 三大城邦争夺蒸汽矿脉。
- 火车与机甲是主要交通与战斗单位。

## 战斗规则
- 决斗采用回合制，爆炸物有范围效果。
- 重伤会触发持续 debuff。

## 关键资源
- 蒸汽核心：高级装备升级材料。
- 冷凝药剂：可解除过热状态。
```

## 6. 与运行时关系

- `plugins` 仅决定默认启用集合。
- 用户仍可在插件面板手动开关（受 required/dependency 约束）。
- 插件真正行为以 `manifest.json + PLUGIN.md` 为准。

## 7. 版本声明

本文档对应插件规范 v1 与当前运行时实现。
