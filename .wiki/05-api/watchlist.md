# 关注列表接口

> 关注列表 CRUD（每日分析任务的目标来源）。需认证。

源码：`scx_stock/api/v1/watchlist.py`、`scx_stock/storage/repo.py`（watchlist 系列）。

---

## 1. `GET /api/v1/watchlist` — 获取列表

无参数。

**响应 `data`**：`list[{code, name, sort_order}]`（按 `sort_order` 升序）

---

## 2. `POST /api/v1/watchlist` — 添加关注

**请求体**：`{code: str, name: str = ""}`

**响应 `data`**：`{code, name}`

> upsert：code 已存在则更新 name。

---

## 3. `DELETE /api/v1/watchlist/{code}` — 移除关注

| 参数 | 位置 | 说明 |
|------|------|------|
| `code` | path | 代码 |

**响应 `data`**：`{deleted: int}`（删除行数）

---

## 4. `PUT /api/v1/watchlist` — 整体替换

**请求体**：

```json
{
  "items": [
    { "code": "510300", "name": "沪深300ETF", "sort_order": 0 },
    { "code": "159915", "name": "", "sort_order": 1 }
  ]
}
```

`WatchlistItem`：`{code: str, name: str = "", sort_order: int = 0}`

**响应 `data`**：`{count: int}`

> 事务内 delete-all + bulk insert。

---

## 5. 数据流

```text
前端 PUT /watchlist  →  repo.replace_watchlist  →  DB watchlist 表
                                                        ↓
调度任务 daily_analysis 读取  repo.list_watchlist_codes()  →  分析目标
```

> 若 DB 关注列表为空，分析任务回退到 `SCX_WATCHLIST` 环境变量。

---

## Related

- [API 总览](overview.md)
- [数据模型](../06-data/data-model.md)
- [调度任务](../07-analysis-scheduler/scheduler.md)
