# AI GameStudio Plugin Spec v1

本文档定义 AI GameStudio 当前唯一有效的插件规范（`schema_version: "1.0"`）。

## 1. 设计原则

- 单一事实源：机器可读配置在 `manifest.json`，LLM 行为手册在 `PLUGIN.md`。
- 单一版本：只支持插件规范 v1，不存在历史版本分支或 fallback 行为。
- 可组合：插件可声明依赖、默认启用、替代关系（`supersedes`）。
- 可验证：插件必须可通过 `PluginEngine.validate()`。

## 2. 目录结构

内置插件（推荐）

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

外部插件（导入）

```text
<plugin>/
  manifest.json
  PLUGIN.md
  prompts/...
  scripts/...
  schemas/...
  README.md   # 建议提供
```

## 3. manifest.json（必需）

### 3.1 最小示例

```json
{
  "schema_version": "1.0",
  "name": "combat",
  "version": "0.1.0",
  "type": "gameplay",
  "required": false,
  "description": "Unified combat system",
  "dependencies": ["state"],
  "prompt": {
    "position": "pre-response",
    "priority": 70,
    "template": "prompts/combat-instruction.md"
  },
  "capabilities": {},
  "blocks": {},
  "events": {"emit": [], "listen": []},
  "storage": {"keys": []}
}
```

### 3.2 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 固定为 `"1.0"` |
| `name` | string | 插件名，必须与目录名一致 |
| `version` | string | 插件版本（建议 semver） |
| `type` | string | `global` 或 `gameplay` |
| `required` | boolean | 是否强制启用 |
| `description` | string | 插件简介 |

### 3.3 常用可选字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `dependencies` | string[] | 依赖插件列表 |
| `default_enabled` | boolean | 默认启用 |
| `supersedes` | string[] | 启用后抑制的旧插件名 |
| `prompt` | object | 提示词注入配置 |
| `capabilities` | object | 能力声明（如脚本能力） |
| `blocks` | object | block 定义（指令/schema/ui/handler） |
| `events` | object | 事件声明 |
| `storage` | object | 插件存储 key 声明 |
| `permissions` | object | 权限声明（network/filesystem/script） |
| `extensions` | object | 扩展配置（如 runtime_settings） |
| `i18n` | object | 多语言展示文案 |
| `max_triggers` | integer | 每会话触发上限 |

## 4. PLUGIN.md（必需）

`PLUGIN.md` 用于给 Plugin Agent 提供高层策略和操作示例，不承担机器校验契约。

建议 frontmatter 字段：

- `name`
- `description`
- `when_to_use`
- `avoid_when`
- `capability_summary`

## 5. Block 定义（manifest.blocks）

每个 block 类型可声明：

- `instruction`: 给 LLM 的输出指引
- `schema`: JSON Schema（内联 object 或外部 schema 路径）
- `handler`: 声明式处理动作（如 `storage_write`、`emit_event`、`builtin`）
- `ui`: 前端渲染信息（`component`、`renderer_name` 等）
- `requires_response`: 是否阻塞用户继续输入

### 5.1 schema 写法

- 内联：`"schema": { ... }`
- 外部：`"schema": "schemas/blocks/<name>.json"`

## 6. Capability 定义（manifest.capabilities）

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

- `script` 路径必须位于插件目录内。
- 越界路径（`../`）会在校验阶段失败。

## 7. Plugin Agent 工具集（平台内置）

当前固定 7 个工具：

1. `update_and_emit`
2. `emit_block`
3. `db_read`
4. `db_log_append`
5. `db_log_query`
6. `db_graph_add`
7. `execute_script`

不支持历史工具名。

## 8. 运行时启用规则

最终启用集合由以下来源合并：

1. `required=true`
2. 项目世界观 frontmatter 的 `plugins: [...]`
3. `default_enabled=true`
4. 用户在插件面板显式开关
5. 依赖自动补全
6. `supersedes` 抑制（可被用户显式启用覆盖）

## 9. 校验清单

通过 `mise run plugin:validate` 时，至少满足：

- 存在 `PLUGIN.md` 与 `manifest.json`
- `schema_version == "1.0"`
- `manifest.name == 目录名`
- 依赖插件可解析
- prompt template 路径不越界且文件存在
- script capability 路径不越界且文件存在

## 10. 兼容性策略

- 当前仅维护插件规范 v1。
- 不保留多版本 schema 分支或旧版本 fallback 逻辑。
- 插件升级通过同版本内字段演进完成。
