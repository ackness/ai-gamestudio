统一使用 `emit` 输出结构化结果。

推荐一次调用完成：
- `items`: 输出 `guide` 或 `choices`。

示例：
```json
{
  "items": [
    {
      "type": "guide",
      "data": {
        "categories": [
          {"style": "safe", "suggestions": ["先观察敌人的布防"]}
        ]
      }
    }
  ]
}
```
