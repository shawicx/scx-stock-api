# 持久化与存储

> DB 引擎/会话生命周期、自动建库、`repo.py` 函数清单、持久化策略。

源码：`scx_stock/storage/db.py`、`scx_stock/storage/repo.py`。

---

## 1. DB 生命周期（`storage/db.py`）

### 1.1 单例

- `_engine`（`db.py:25`）、`_session_factory`（`db.py:26`）模块级单例
- `get_engine()`（`:29`）惰性创建 `create_async_engine(get_dsn(), echo=...)`
- `get_session_factory()`（`:40`）惰性创建 `async_sessionmaker(expire_on_commit=False)`
- `get_session()`（`:53`）FastAPI 依赖：`async with factory() as session: yield session`
- `close_db()`（`:154`）`await _engine.dispose()`，重置两个单例

### 1.2 自动建库 `init_db()`（`db.py:129`）

```text
init_db():
  1. import models（注册表）
  2. engine.begin() → conn.run_sync(Base.metadata.create_all)
  3. 若捕获 "database missing" 错误（asyncpg InvalidCatalogNameError）：
       若 settings.db_auto_create=true：
         → _create_database_if_missing()  # 连 postgres 库 CREATE DATABASE
         → close_db()                     # 丢弃旧连接池
         → 重建 engine → 再次 create_all
       否则：只 warning
  4. 任何异常都只 warning，不阻断启动
```

`_create_database_if_missing()`（`db.py:100`）通过 `asyncpg.connect`（autocommit，DDL 不能在事务内）连维护库 `postgres`，查 `pg_database`，不存在则 `CREATE DATABASE`。

> **重要**：`init_db()` 在 lifespan 启动时调用，失败只记 warning。便于无 DB 环境调试 Provider/缓存路径。

---

## 2. repo.py 函数清单（`storage/repo.py`）

全部 async，通过 `get_session_factory()` 获取会话。PostgreSQL `ON CONFLICT DO UPDATE` 批量 upsert。读函数吞异常返回空/None。

### 股票

| 函数 | 说明 |
|------|------|
| `upsert_stocks(rows)` | 批量 upsert（`BATCH_SIZE=5000`），冲突更新 name/market/pinyin |
| `load_all_stocks()` | 全表加载 |
| `count_stocks()` | 计数（`/health/ready` 用） |
| `clear_all_stocks()` | 清空 |

### 行业

| 函数 | 说明 |
|------|------|
| `upsert_stock_industries(rows)` | 批量 upsert（`BATCH_SIZE=2000`），冲突更新 industry |
| `load_all_industries()` | 返回 `{code: industry}` 字典；DB 失败返回 `{}` |

### 应用配置（KV）

| 函数 | 说明 |
|------|------|
| `get_all_settings()` | 返回 `{key: value}`；失败返回 `{}` |
| `upsert_settings(items)` | 冲突更新 value |

### 关注列表

| 函数 | 说明 |
|------|------|
| `list_watchlist()` | 按 sort_order 升序；失败返回 `[]` |
| `list_watchlist_codes()` | 仅 codes |
| `add_watchlist(code, name, sort_order)` | upsert（code 冲突更新 name/sort_order） |
| `remove_watchlist(code)` | 删除，返回行数 |
| `clear_watchlist()` | 清空 |
| `replace_watchlist(items)` | 事务内 delete-all + bulk insert |

### 分析报告

| 函数 | 说明 |
|------|------|
| `upsert_analysis_reports(reports)` | 跳过 `trade_date is None`；冲突更新标量列 + payload |
| `load_latest_reports(codes)` | 每 code 取 `max(trade_date)` 最新；从 payload JSONB 重建 AnalysisReport |
| `load_reports_by_date(trade_date)` | 该日全部报告 |
| `load_report_history(code, limit=30)` | 按日期降序历史 |

### K 线

| 函数 | 说明 |
|------|------|
| `upsert_klines(rows)` | 冲突更新 OHLCV |
| `load_kline(code, days=120)` | 读最近 N 天（降序读后反转升序）；失败返回 None（调用方 fallback Provider） |
| `get_kline_last_date(code)` | `max(trade_date)`，增量同步用 |

### 交易日历

| 函数 | 说明 |
|------|------|
| `upsert_calendar(rows)` | 冲突更新 is_open |
| `is_trading_day(d=None)` | DB 查询；DB 不可用或无记录 → 回退 `weekday() < 5` |

> `is_trading_day` 被 `daily_analysis_job` 用作交易日门控。

### 授权码

| 函数 | 说明 |
|------|------|
| `create_auth_code(code, expires_at)` | upsert，设 `is_active=True` + `expires_at` |
| `validate_auth_code(code)` | 存在 + active + 未过期 → True（时区安全：naive DB 时间当 UTC）；DB 错误 fail-closed 返回 False |
| `deactivate_auth_code(code)` | 设 `is_active=False`（logout 用） |

---

## 3. 持久化策略

| 数据 | 变化速度 | 存储 | 写入时机 |
|------|---------|------|---------|
| 实时行情 | 秒级 | Redis（30s/120s TTL） | 实时 |
| 搜索索引 | 日级 | 内存（DB 源） | 每日 09:20 / `/admin/reindex` |
| 股票/ETF 列表 | 日级 | DB + Redis | 每日 09:00 |
| 行业映射 | 日级 | DB | 每日 09:15 |
| K 线 | 日级 | DB | 每日 16:00 增量 |
| 交易日历 | 周/年级 | DB | 每周一 06:00 |
| 分析报告 | 日级 | DB | 每日 21:00 |
| 关注列表 | 用户级 | DB | 前端 CRUD |
| 应用配置 | 用户级 | DB | 前端 `/settings` |

> **K 线 DB 优先读**：分析时先 `repo.load_kline`，不足 30 根才 fallback Provider 拉取并 `upsert_klines` 回填 DB。

---

## Related

- [数据模型](data-model.md)
- [缓存策略](../04-data-providers/cache.md)
- [调度任务](../07-analysis-scheduler/scheduler.md)
- [分析引擎](../07-analysis-scheduler/analysis-engine.md)
