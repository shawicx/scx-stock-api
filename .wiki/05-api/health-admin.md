# 健康检查与运维接口

> 存活/就绪探针、手动同步、索引重建、任务轮询。`/health*` 公开；`/admin/*` 需认证。

源码：`scx_stock/main.py`（`_register_health`、`_register_admin`）、`scx_stock/scheduler/task_manager.py`。

---

## 1. 健康检查（公开）

### `GET /health` — 存活探针

无参数。进程在跑即返回 ok。

**响应 `data`**：`{status: "ok", version: "0.1.0"}`

### `GET /health/ready` — 就绪探针

无参数。探测缓存与 DB 依赖。

**响应 `data`**：

```json
{
  "status": "ok",
  "checks": {
    "cache": "ok",
    "db": "ok (5400 rows)"
  }
}
```

- `status`：全绿 `"ok"`，否则 `"degraded"`
- `checks.cache`：`get_cache()` 可用 → `"ok"`，否则 `"fail: ..."`
- `checks.db`：`repo.count_stocks()` 成功 → `"ok (N rows)"`，否则 `"fail: ..."`

---

## 2. 运维端点（需认证）

### `POST /admin/sync` — 全量同步（异步）

无参数。提交后台任务，串行执行：股票列表 → ETF 列表 → 行业映射 → 重建搜索索引。

**响应 `data`**：`{task_id: str}`

> 异步执行，通过 `GET /admin/task/{task_id}` 轮询进度。

### `POST /admin/reindex` — 重建搜索索引

无参数。同步从 DB 全量加载重建内存索引。

**响应**：成功 `ok({index_size: int, ...})`；失败 `{code: 1, message: "reindex failed: ...", data: null}`

### `GET /admin/task/{task_id}` — 查询任务状态

| 参数 | 位置 | 说明 |
|------|------|------|
| `task_id` | path | `POST /admin/sync` 返回的 id |

**响应 `data`**（`TaskInfo`，`task_manager.py:28`）：

```json
{
  "task_id": "1723456789000",
  "name": "全量同步",
  "status": "running",
  "progress": "正在同步 ETF 列表...",
  "result": null,
  "error": "",
  "created_at": 1723456789.0,
  "elapsed": 3.2
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 毫秒时间戳 |
| `name` | str | 任务名 |
| `status` | enum | `pending` / `running` / `done` / `failed` |
| `progress` | str | 进度描述 |
| `result` | dict\|null | 完成后的结果 |
| `error` | str | 失败原因 |
| `created_at` | float | 创建时间戳 |
| `elapsed` | float | 已耗时秒（pending/running 实时计算） |

> 任务不存在：`{code: 1, message: "task not found: <id>", data: null}`

---

## 3. TaskManager（`scheduler/task_manager.py`）

- 内存级异步任务管理（单进程，不跨进程）
- `submit(name, coro_factory)`：生成毫秒时间戳 task_id，`asyncio.create_task` 运行
- 状态流转：`PENDING → RUNNING → DONE | FAILED`
- `TaskHandle.update_progress` 报告进度
- `list_tasks()` 按时间倒序
- 仅 `/admin/sync` 触发的全量同步使用此机制

---

## Related

- [API 总览](overview.md)
- [调度任务](../07-analysis-scheduler/scheduler.md)
- [代码结构](../03-codebase/codebase.md)
