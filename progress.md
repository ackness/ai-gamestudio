Original prompt: 检查一下现在的代码在前端 如果是准备开始冒险的页面的时候 如果刷新则会创建一个新的session, 帮我修改这个逻辑, 无论怎么刷新一个新的session已有的情况下不用新建session

## 2026-02-16
- 已定位问题在 `frontend/src/pages/ProjectEditorPage.tsx`：在 sessions 首次拉取未完成时，`sessions` 仍为空数组，自动创建逻辑提前触发，导致刷新时重复新建 session。
- 计划：在 session store 增加“sessions 首次加载完成”状态，自动创建逻辑仅在该状态为 true 后执行。
- 已修改 `frontend/src/pages/ProjectEditorPage.tsx`：新增 `sessionsFetched` 状态，自动创建与自动选中逻辑都等待 `fetchSessions` 完成后再执行。
- 项目 ID 变化时重置 `sessionsCheckedRef` 与 `sessionsFetched`，避免刷新或切换时误判导致重复创建。
- 执行 `npm run build`（frontend）验证：本次改动文件通过语法检查，但项目当前存在既有 TypeScript 报错（例如 `GamePanel.tsx`、`FormRenderer.tsx`、`DebugLogPanel.tsx`），构建未通过；这些与本次 session 刷新修复无直接关系。

### TODO (next agent)
- 可选：补一条前端集成测试，覆盖“已有 session 时刷新不触发 createSession”。
- 可选：清理当前项目中既有 TS 报错，恢复 `npm run build` 全绿。
- 二次构建确认：错误列表与首次一致，未引入新的 TypeScript 报错。

## 2026-02-16 (build error fix)
- 修复 `DebugLogPanel.tsx`：避免在 JSX 条件表达式中直接传播 `unknown`，先提取并判空后再渲染。
- 修复 `FormRenderer.tsx`：补上 `locked` props 解构；新增 `getTextualValue` 保障 input/select/textarea 的 `value` 类型稳定为 `string | number`。
- 修复 `GamePanel.tsx`：移除未使用变量 `configSource`；为 `state.world`/`state.characters` 增加类型收敛；为 `event` block 增加 `isGameEvent` 类型守卫。
- 修复 `GenericBlockRenderer.tsx`：移除未使用参数 `data`（`renderSection`）。
- 结果：`npm run build` 成功（TypeScript 报错已清零）；仅有 Node 版本提示（当前 Node 18.8.0，Vite 推荐 20.19+）。

## 2026-02-17 (story-image plugin)
- 新增插件 `plugins/story-image/`，定义 `json:story_image` block schema、提示词模板与 builtin handler 绑定。
- 后端新增 `backend/app/services/image_service.py`：
  - 解析项目/环境图片配置（`IMAGE_GEN_*` + 项目级覆盖）。
  - 调用 `https://api.whatai.cc/v1/chat/completions` 兼容格式并提取图片 URL/base64。
  - 以 `PluginStorage` 按 session 保存图片记录（包含 continuity 参考、重生成关系）。
  - 提供 `generate_story_image` 与 `regenerate_story_image`。
- 后端 `block_handlers` 新增 `story_image_builtin`，仅在插件声明动作触发时执行（避免插件禁用时误生效）。
- `chat_service` 注入 `story_images` 上下文供后续图片连续性参考。
- `chat` websocket 的 `block_response` 新增 `story_image` 重生成分支，支持：
  - 通过已有 `image_id` 重生成。
  - 在初次失败无 `image_id` 时，使用 block 原始字段直接重试生成。
- 扩展项目配置与安全存储：
  - `Project` 模型、`/api/projects` create/update/read、DB migrate、SecretStore 迁移均增加 `image_model/image_api_key/image_api_base`。
  - API 仅暴露 `has_image_api_key`，不回传明文密钥。
- 前端新增 `StoryImageRenderer`，在 `GameSession` 消息流中显示图片，并提供“Regenerate image”按钮。
- 前端模型配置面板新增图片模型/API Key/API Base 设置项。
- 新增测试脚本 `scripts/test_image_generation_format.py`，可直接验证第三方接口响应并标准化输出解析结果。
- 测试结果：
  - `uv run pytest backend/tests/test_story_image_service.py backend/tests/test_api_llm_security.py` 通过。
  - `uv run pytest backend/tests/test_plugin_engine.py backend/tests/test_block_handlers_declarative.py backend/tests/test_chat_service.py` 通过。
  - `uv run pytest backend/tests/test_api_projects.py` 通过。
  - `cd frontend && npm run build` 通过（提示 Node 版本低于 Vite 推荐，但本次构建成功）。

### TODO (next agent)
- 联调真实图片接口时，确认供应商返回格式是否还存在额外变体，必要时继续扩展 `_extract_image_payload`。
- 可选：为 `story_image` 增加前端视觉占位（加载中 skeleton）与失败提示的更细粒度状态。
- 可选：增加端到端测试覆盖 websocket 重生成流程（`block_response -> done -> story_image -> turn_end`）。

## 2026-02-17 (alerts panel render loop fix)
- 修复 `NotificationPanel` 点击 Alerts 后出现 `Maximum update depth exceeded` 的循环更新问题。
- 根因修复：
  - 避免在 zustand selector 中直接 `filter` 生成新数组（每次渲染返回新引用，叠加 effect 写入容易触发循环）。
  - `markAllRead` 改为支持按 session 标记，且仅在目标 session 存在未读时才写入。
- 修改文件：
  - `frontend/src/stores/notificationStore.ts`
  - `frontend/src/components/status/NotificationPanel.tsx`
- 验证：
  - `cd frontend && npm run build` 通过。
  - `cd frontend && npm run test:unit` 通过（含 `notification-store.test`）。

## 2026-02-17 (image base64 content parser enhancement)
- 根据样本 `data/raw_response_1771317200.json` 增强图片解析：
  - 支持从 markdown 文本 `![image](data:image/...;base64,...)` 直接提取。
  - 支持 `content` 为数组时，从 `text` 项里提取 data URL/base64。
  - 支持“纯 base64 无 data:image 前缀”自动识别图片头（PNG/JPEG/GIF/WebP）并补成 data URL。
- 修改文件：
  - `backend/app/services/image_service.py`
  - `backend/tests/test_image_payload_parser.py`（新增）
- 验证：
  - `uv run pytest backend/tests/test_image_payload_parser.py backend/tests/test_story_image_service.py` 通过。
  - 用真实样本 `data/raw_response_1771317200.json` 本地调用 `_extract_image_payload` 可成功提取 `data:image/png;base64,...`。

## 2026-02-17 (generic runtime settings system)
- 实现通用 Runtime Settings 架构（非单插件）：
  - 后端新增 `backend/app/services/runtime_settings_service.py`：
    - 从插件 `extensions.runtime_settings.fields` 自动收集 schema。
    - 支持 `project/session` 作用域覆盖（`session` 可覆盖 `project`）。
    - 类型校验与归一化（string/number/integer/boolean/enum）。
    - 输出合并后的 `values`、`by_plugin`、overrides。
    - 提供轻量模板渲染 `{{var}}` 与 DM runtime settings prompt 块构建。
  - 新增 API：`backend/app/api/runtime_settings.py`
    - `GET /api/runtime-settings/schema`
    - `GET /api/runtime-settings`
    - `PATCH /api/runtime-settings`
  - `backend/app/main.py` 已注册 runtime settings router。
- 插件声明扩展：
  - `plugins/core-blocks/PLUGIN.md`：叙事语气/节奏/长度/风险倾向。
  - `plugins/choices/PLUGIN.md`：选项数量/风格。
  - `plugins/auto-guide/PLUGIN.md`：类别数量/建议风格/wild 开关。
  - `plugins/story-image/PLUGIN.md`：风格 preset、自定义模板、negative prompt、参考帧数量、strict continuity。
- 提示词模板接入运行时设置：
  - `plugins/core-blocks/prompts/core-instruction.md`
  - `plugins/choices/prompts/choices-instruction.md`
  - `plugins/auto-guide/prompts/guide-instruction.md`
  - `plugins/story-image/prompts/story-image-instruction.md`
- 运行链路接入：
  - `backend/app/services/chat_service.py` 将 runtime settings 注入 prompt context（`runtime_settings` / `runtime_settings_flat`）并追加 settings 指令块。
  - `backend/app/services/image_service.py` 读取通用 runtime settings 并影响图片生成：
    - 支持 `prompt_template`（含 `{{story_background}}`、`{{frame_prompt}}` 等变量）。
    - 支持 style preset / negative prompt / reference_count / strict_continuity。
    - 每张图片记录保存 `runtime_settings` 快照，响应中返回 `settings_applied`。
- 前端通用设置面板：
  - 新增 `frontend/src/components/status/RuntimeSettingsPanel.tsx`（schema 驱动渲染，支持 project/session scope、字段级实时 PATCH、Reset）。
  - `frontend/src/components/status/SidePanel.tsx` 新增 `Settings` 标签页。
  - `frontend/src/services/api.ts`、`frontend/src/types/index.ts` 增加 runtime settings 类型与 API。
- 新增测试：
  - `backend/tests/test_runtime_settings_service.py`
  - `backend/tests/test_api_runtime_settings.py`
- 验证：
  - `uv run pytest backend/tests/test_runtime_settings_service.py backend/tests/test_api_runtime_settings.py` 通过。
  - `uv run pytest backend/tests/test_chat_service.py backend/tests/test_story_image_service.py backend/tests/test_image_payload_parser.py backend/tests/test_api_llm_security.py backend/tests/test_api_projects.py` 通过。
  - `cd frontend && npm run build && npm run test:unit` 通过（Node 版本仍有 Vite 推荐提示，但构建成功）。

### TODO (next agent)
- 可选：为 runtime settings 增加 websocket `settings_updated` 广播，支持多标签页同步刷新。
- 可选：增加 “Prompt Preview” API/UI（尤其 story-image 模板调试）。
- 可选：在设置面板做输入防抖和批量提交模式，减少逐键 PATCH 请求频率。

## 2026-02-17 (story-image visibility improvement)
- 现象排查结论：
  - `story-image` 插件已启用，但最近会话中模型未产出 `json:story_image` block（数据库中仅有 guide/character_sheet，无 story_image 记录），因此前端没有图片可显示。
- 体验修复：
  - 新增 Quick Action 按钮：`输出配图`（前端）
    - 文件：`frontend/src/components/game/QuickActions.tsx`
    - 触发 backend `force_trigger` 的 `story_image`，可手动强制让模型输出 `json:story_image`。
  - backend `force_trigger` 增加 `story_image` 指令模板
    - 文件：`backend/app/api/chat.py`
  - `story-image` runtime settings 新增 `emit_mode`（`key_moments` / `every_turn`）
    - 文件：`plugins/story-image/PLUGIN.md`
  - 强化 story-image 提示词模板：
    - 支持 `emit_mode=every_turn` 时强制每轮输出配图；
    - `key_moments` 模式下在无历史配图时更偏向先输出首图。
    - 文件：`plugins/story-image/prompts/story-image-instruction.md`
- 验证：
  - `uv run pytest backend/tests/test_plugin_engine.py backend/tests/test_chat_service.py backend/tests/test_runtime_settings_service.py` 通过。
  - `cd frontend && npm run build && npm run test:unit` 通过。
