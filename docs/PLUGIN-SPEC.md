# AI GameStudio Plugin Spec v1

本文档定义 AI GameStudio 当前唯一有效插件规范（`schema_version: "1.0"`）。

## 1. 规范边界

- 单一版本：只支持 v1，不存在 v2/v3 fallback 分支。
- 单一契约：插件必须同时提供 `manifest.json + PLUGIN.md`。
- 单一工具集：Plugin Agent 只暴露固定 7 个工具。

## 2. 目录布局

当前 `PluginEngine` 支持两种布局：

分组布局（推荐）：

```text
plugins/
  <group>/
    group.json
    <plugin>/
      manifest.json
      PLUGIN.md
      prompts/...
      scripts/...
      schemas/...
```

平铺布局（兼容）：

```text
plugins/
  <plugin>/
    manifest.json
    PLUGIN.md
```

外部导入插件最小要求：

```text
<plugin>/
  manifest.json
  PLUGIN.md
```

## 3. `manifest.json`（必需）

### 3.1 最小示例

```json
{
  "schema_version": "1.0",
  "name": "combat",
  "version": "0.1.0",
  "type": "gameplay",
  "required": false,
  "description": "Unified combat system"
}
```

### 3.2 必填字段与约束

| 字段 | 类型 | 约束 |
|---|---|---|
| `schema_version` | string | 必须等于 `"1.0"` |
| `name` | string | 必须与目录名一致；仅小写字母/数字/短横线 |
| `version` | string | 插件版本（建议 semver） |
| `type` | string | 仅允许 `global` 或 `gameplay` |
| `required` | boolean | 是否强制启用 |
| `description` | string | 描述文案 |

### 3.3 常用可选字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `dependencies` | string[] | 依赖插件 |
| `default_enabled` | boolean | 默认启用 |
| `supersedes` | string[] | 启用后抑制其他插件 |
| `prompt` | object | 模板路径、注入位置、优先级 |
| `blocks` | object | block 声明（instruction/schema/handler/ui） |
| `capabilities` | object | 能力声明（含 script） |
| `extensions` | object | 扩展配置（runtime settings 等） |
| `i18n` | object | 多语言文案 |
| `max_triggers` | integer | 每会话触发上限 |

## 4. `PLUGIN.md`（必需）

`PLUGIN.md` 面向 LLM 行为，不替代机器契约。

建议 frontmatter 字段：

- `name`
- `description`
- `when_to_use`
- `avoid_when`

说明：

- 若 `PLUGIN.md` 里写了 `name/version`，校验时会与 `manifest.json` 进行一致性检查。

## 5. Block 声明（`manifest.blocks`）

每个 block 类型可声明：

- `instruction`
- `schema`
- `handler`
- `ui`
- `requires_response`

### 5.1 `schema` 写法

- 内联：`"schema": { ... }`
- 外部路径：`"schema": "schemas/blocks/<name>.json"`

当前实现说明：

- 运行时校验支持内联 schema。
- `GET /api/plugins/block-schemas` 当前返回内联 schema（`decl.schema`）；若仅填路径字符串，前端不会拿到展开后的 schema。

### 5.2 声明式 handler 动作

`dispatch_block()` 当前支持的声明式 action：

- `builtin`
- `storage_write`
- `emit_event`
- `update_character`
- `create_event`

## 6. Capability 声明（`manifest.capabilities`）

脚本能力示例：

```json
{
  "dice.roll": {
    "description": "Roll dice",
    "implementation": {
      "type": "script",
      "script": "scripts/roll.py",
      "timeout_ms": 5000
    },
    "result_block_type": "dice_result"
  }
}
```

约束：

- `implementation.type = "script"` 时，`script` 必须在插件目录内。
- 越界路径（如 `../`）会在校验阶段失败。

## 7. Runtime Settings 扩展

声明入口：`manifest.extensions.runtime_settings`。

推荐写法（当前运行时主写法）：

```json
{
  "extensions": {
    "runtime_settings": {
      "fields": {
        "style_preset": { "type": "enum", "default": "cinematic" }
      }
    }
  }
}
```

兼容写法：

- `settings: [{ key: "...", ... }]` 仍可接受。
- `manifest_to_metadata()` 会自动归一化成 `fields` 结构。

## 8. Plugin Agent 工具集（固定）

1. `update_and_emit`
2. `emit_block`
3. `db_read`
4. `db_log_append`
5. `db_log_query`
6. `db_graph_add`
7. `execute_script`

不支持历史工具名。

## 9. 启用规则

最终启用集由以下来源合并：

1. `required=true`
2. 世界文档 frontmatter `plugins`
3. `default_enabled=true`
4. 用户显式开关
5. 依赖自动补全
6. `supersedes` 抑制（用户显式启用可覆盖）

## 10. 校验清单

`mise run plugin:validate` 至少检查：

- `PLUGIN.md` 与 `manifest.json` 均存在
- `schema_version == "1.0"`
- `manifest.name == 目录名`
- 依赖插件可解析
- prompt template 路径合法且文件存在
- script capability 路径合法且文件存在
- `PLUGIN.md` 与 manifest 的 `name/version` 一致性（若声明）

## 11. 兼容性策略

- 插件系统按单版本 v1 维护。
- 不保留多版本 schema 分支或旧版本 fallback 逻辑。
