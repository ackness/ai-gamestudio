统一使用 `emit` 完成本回合的写库与结构化输出。

推荐一次调用完成：
1. `writes`：写入角色/世界/场景状态。
2. `logs`：追加日志（可选）。
3. `items`：输出结构列表。

最小示例：
```json
{
  "writes": [{"collection": "characters", "key": "hero", "value": {"name": "Ayla"}}],
  "items": [{"type": "notification", "data": {"level": "info", "content": "已更新角色状态"}}]
}
```
