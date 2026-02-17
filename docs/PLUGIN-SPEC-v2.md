# AI GameStudio Plugin Spec v2.0（Skill-First 执行规范）

> 本文是 V2 运行规范文档，不是介绍文档。
>
> 与 v1 的关系：v2 替代运行规范；v1 插件不再直接运行。

---

## 1. 规范定位

1. 这是执行规范（runtime contract），不是产品介绍文档。
2. 规范目标是“实现无决策空白”，实现者按本文可直接编码。
3. `manifest.json` 是唯一事实源；`PLUGIN.md` 是 LLM 运行手册。

---

## 2. 必需文件与职责

每个 V2 插件目录必须包含：

1. `PLUGIN.md`（required）：LLM 运行手册。
2. `README.md`（required）：人类文档。
3. `manifest.json`（required）：机器事实源。
4. `schemas/`（required）：结构化契约目录。

最小目录：

```text
my-plugin/
├── PLUGIN.md
├── README.md
├── manifest.json
└── schemas/
```

---

## 3. `manifest.json` 规范

## 3.1 必填字段

```json
{
  "schema_version": "agsp-v2",
  "name": "dice-roll",
  "version": "2.0.0",
  "type": "gameplay",
  "required": false,
  "dependencies": ["core-blocks"],
  "capabilities": ["dice.roll", "plugin.script"],
  "permissions": {
    "network": false,
    "filesystem_scope": ["plugin", "data"],
    "script_languages": ["python"]
  },
  "entry": {
    "plugin_md": "PLUGIN.md",
    "readme": "README.md"
  },
  "schema_index": "schemas/index.yaml"
}
```

## 3.2 字段定义

1. `schema_version`：固定为 `agsp-v2`。
2. `name`：插件唯一名，必须与目录名一致。
3. `version`：插件版本，建议 semver。
4. `type`：`global | gameplay`。
5. `required`：是否必需插件。
6. `dependencies`：插件依赖列表。
7. `capabilities`：可调用能力声明。
8. `permissions`：权限声明。
9. `entry`：入口文件声明。
10. `schema_index`：可选；缺失时启用扫描回退。

## 3.3 权限默认（若 manifest 未显式声明）

1. 网络：按插件类型默认
   1. `global`: allow
   2. `gameplay`: deny
2. 文件系统：`plugin + data`。
3. 脚本语言：首期仅 `python`。

---

## 4. `PLUGIN.md` frontmatter 规范

## 4.1 必填字段

```yaml
---
name: dice-roll
description: 处理骰子检定与概率判定。
version: 2.0.0
when_to_use:
  - 需要随机判定
  - 需要命中/豁免计算
avoid_when:
  - 纯叙事无检定
capability_summary: 提供骰子解析、执行与结构化结果输出能力。
---
```

## 4.2 一致性规则

1. `PLUGIN.md.name` 必须等于 `manifest.json.name`。
2. `PLUGIN.md.version` 必须等于 `manifest.json.version`。
3. 任一不一致，导入失败。

## 4.3 触发语义

1. `when_to_use`：规则匹配正向条件。
2. `avoid_when`：规则匹配负向条件。
3. `capability_summary`：LLM 选择能力时的摘要提示。

---

## 5. `PLUGIN.md` 正文推荐章节

插件正文建议固定以下章节，用于运行期按需加载：

1. `# Purpose`
2. `# Activation Rules`
3. `# Execution Workflow`
4. `# Script Usage`
5. `# Output Contract`
6. `# Fallback`
7. `# References`

运行时要求：

1. 必须优先遵守 `Execution Workflow`。
2. 必须按 `Output Contract` 产出结构化 block。
3. 脚本失败时必须按 `Fallback` 处理。

---

## 6. `schemas/` 规范

## 6.1 索引文件（优先）

支持：

1. `schemas/index.json`
2. `schemas/index.yaml`

索引示例：

```yaml
blocks:
  dice_result: schemas/blocks/dice_result.yaml
ui:
  dice_result: schemas/ui/dice_result_card.yaml
commands:
  dice_roll: schemas/commands/dice_roll.json
templates:
  dice_roll: schemas/templates/dice_roll.yaml
```

## 6.2 扫描回退（无索引时）

固定扫描目录：

1. `schemas/blocks/`
2. `schemas/ui/`
3. `schemas/commands/`
4. `schemas/templates/`

## 6.3 JSON/YAML 双支持

1. 支持扩展名：`.json`、`.yaml`、`.yml`。
2. 解析后统一转为内部 JSON Schema 表示。
3. 同名冲突时规则：索引声明优先；索引缺失时按文件名冲突报错。

---

## 7. 协议规范

## 7.1 `json:plugin_use` JSON Schema

```json
{
  "type": "object",
  "required": ["plugin", "capability", "args"],
  "properties": {
    "plugin": {"type": "string", "minLength": 1},
    "capability": {"type": "string", "minLength": 1},
    "args": {"type": "object"},
    "mode": {
      "type": "string",
      "enum": ["sync", "async"],
      "default": "sync"
    }
  },
  "additionalProperties": false
}
```

## 7.2 `json:plugin_script` JSON Schema

```json
{
  "type": "object",
  "required": ["plugin", "script", "input"],
  "properties": {
    "plugin": {"type": "string", "minLength": 1},
    "script": {"type": "string", "pattern": "^scripts/"},
    "input": {"type": "object"},
    "timeout_ms": {"type": "integer", "minimum": 100, "maximum": 60000}
  },
  "additionalProperties": false
}
```

---

## 8. 脚本执行规范

## 8.1 语言范围

1. Phase 1 仅允许 Python。
2. 非 Python 调用在运行时校验阶段拒绝。

## 8.2 命令白名单来源

白名单来源必须一致：

1. `manifest.json` 的 `capabilities/permissions`。
2. `PLUGIN.md` 的能力摘要与执行说明。

如果两者语义冲突，导入失败。

## 8.3 审计字段

每次执行必须记录：

1. `invocation_id`
2. `plugin`
3. `script`
4. `args`
5. `exit_code`
6. `duration`
7. `stdout`
8. `stderr`

---

## 9. 安全规范

## 9.1 默认确认策略

1. 默认无需确认（开发效率优先）。
2. 但必须记录完整审计日志。

## 9.2 网络默认

按插件类型默认：

1. `global`：默认允许。
2. `gameplay`：默认拒绝。

## 9.3 文件访问默认范围

1. 插件目录。
2. `data/` 目录。

其他路径默认拒绝。

---

## 10. 校验规则

## 10.1 导入校验

1. 必需文件存在性校验。
2. `manifest.json` 必填字段校验。
3. `PLUGIN.md` frontmatter 必填字段校验。
4. `name/version` 跨文件一致性校验。
5. `schemas` 索引或扫描可解析性校验。
6. 权限与脚本语言策略校验。

## 10.2 运行时校验

1. 插件启用状态。
2. 依赖是否满足。
3. `plugin_use/plugin_script` schema 校验。
4. 能力与权限匹配校验。
5. 脚本路径与文件访问范围校验。

## 10.3 跨文件一致性校验

1. `manifest.entry.plugin_md` 必须指向存在的 `PLUGIN.md`。
2. `manifest.entry.readme` 必须指向存在的 `README.md`。
3. `schema_index` 存在时，索引中路径必须全部可解析。

---

## 11. 迁移规则

1. V1 插件不再直接运行。
2. 内置插件必须先完成 V2 改造。
3. 迁移完成前不得启用 V2 默认运行时。

---

## 12. 最小可用插件示例（4 文件完整示例）

## 12.1 `manifest.json`

```json
{
  "schema_version": "agsp-v2",
  "name": "dice-roll",
  "version": "2.0.0",
  "type": "gameplay",
  "required": false,
  "dependencies": ["core-blocks"],
  "capabilities": ["dice.roll", "plugin.script"],
  "permissions": {
    "network": false,
    "filesystem_scope": ["plugin", "data"],
    "script_languages": ["python"]
  },
  "entry": {
    "plugin_md": "PLUGIN.md",
    "readme": "README.md"
  },
  "schema_index": "schemas/index.yaml"
}
```

## 12.2 `PLUGIN.md`

```markdown
---
name: dice-roll
description: 处理骰子检定与概率判定。
version: 2.0.0
when_to_use:
  - 需要随机判定
avoid_when:
  - 无检定的纯叙事
capability_summary: 解析骰子表达式并输出 json:dice_result。
---

# Purpose
对检定请求生成标准化随机结果。

# Activation Rules
当用户行动涉及概率判定时激活。

# Execution Workflow
1. 解析骰子表达式。
2. 运行 scripts/roll.py。
3. 输出 json:dice_result。

# Script Usage
python scripts/roll.py --expr "2d6+3"

# Output Contract
输出 json:dice_result。

# Fallback
脚本失败时输出 notification，提示手动判定。

# References
复杂规则可读取 references/rules.md。
```

## 12.3 `README.md`

```markdown
# Dice Roll Plugin

用于 RPG 场景中的骰子检定与结果展示。

## 开发调试

- 运行脚本：`python scripts/roll.py --expr "2d6+3"`
- 核验输出：确认能生成 `json:dice_result` 数据结构。
```

## 12.4 `schemas/index.yaml`

```yaml
blocks:
  dice_result: schemas/blocks/dice_result.yaml
ui:
  dice_result: schemas/ui/dice_result_card.yaml
commands:
  dice_roll: schemas/commands/dice_roll.yaml
templates:
  dice_roll: schemas/templates/dice_roll.yaml
```

---

## 13. 公共接口与类型变更（必须同步实现）

1. `GET /api/plugins` 返回新增字段：
   1. `version`
   2. `manifest_source`
   3. `schema_status`
   4. `script_mode`
   5. `network_default`
2. `GET /api/plugins/block-schemas` 的 schema 来源改为 `schemas/`。
3. 新增运行时调用接口：
   1. `POST /api/plugins/runtime/activate`
   2. `POST /api/plugins/runtime/plugin-use`
   3. `POST /api/plugins/runtime/plugin-script`
   4. `GET /api/plugins/runtime/invocations/{invocation_id}`
4. 前端 `Plugin` 类型必须新增对应字段并完整消费，最小定义如下：

```ts
export interface Plugin {
  name: string
  description: string
  type: 'global' | 'gameplay'
  required: boolean
  enabled: boolean
  dependencies: string[]
  version: string
  manifest_source: 'project' | 'library' | 'builtin'
  schema_status: 'ok' | 'index_fallback' | 'missing' | 'invalid'
  script_mode: 'python-only'
  network_default: 'allow' | 'deny'
}
```

---

## 14. 验收与测试场景

1. 一致性场景：`PLUGIN.md` 与 manifest `name/version` 不一致时导入失败。
2. schema 场景：有索引时按索引加载；无索引时扫描回退可用。
3. 协议场景：`plugin_use` 与 `plugin_script` 示例可通过 schema 校验。
4. 安全场景：`gameplay` 插件联网默认拒绝；`global` 插件联网默认允许。
5. 执行场景：脚本访问插件目录与 `data/` 可通过，访问其他路径被拒绝。
6. 回归场景：现有 generic block renderer 链路可继续工作。

---

## 15. 假设与默认值

1. 首期仅 Python。
2. 首期不做插件导出。
3. 首期不做项目级模板覆盖。
4. API 不加 `/v2` 前缀，直接替换旧语义。
5. 本规范中的推荐在首版实现中按必须执行。
