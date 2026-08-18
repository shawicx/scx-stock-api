# 调度任务

> APScheduler 定时同步与分析，时区 Asia/Shanghai。

源码：`scx_stock/scheduler/runner.py`、`sync_jobs.py`、`analysis_job.py`、`task_manager.py`。

---

## 1. 调度配置（`runner.py`）

- **时区**：`Asia/Shanghai`（`runner.py:70`）
- **misfire_grace_time**：600s（`runner.py:89`）
- **触发器**：`CronTrigger.from_crontab`
- `get_scheduler()`（`:109`）单例，首次调用执行 `setup()`
- lifespan 启动时 `scheduler.start()`，关闭时 `scheduler.shutdown()`

---

## 2. 调度计划（7 个任务）

| Job ID | Cron | 函数 | 说明 |
|--------|:---:|------|------|
| `sync_stock_list` | `0 9 * * 1-5` | `sync_all` | 周一至五 09:00，串行：股票+ETF+行业+索引 |
| `sync_etf_list` | `10 9 * * 1-5` | `sync_etf_list` | 周一至五 09:10 |
| `sync_stock_industries` | `15 9 * * 1-5` | `sync_stock_industries` | 周一至五 09:15 |
| `rebuild_search_index` | `20 9 * * 1-5` | `rebuild_search_index` | 周一至五 09:20 |
| `sync_market_calendar` | `0 6 * * 1` | `sync_market_calendar` | 每周一 06:00 |
| `sync_kline` | `0 16 * * 1-5` | `sync_kline` | 周一至五 16:00（收盘后） |
| `daily_analysis` | `0 21 * * 1-5` | `daily_analysis_job` | 周一至五 21:00（`SCX_ANALYSIS_CRON` 可改） |

> `daily_analysis` 的 cron 默认 `None`，回退到 `settings.analysis_cron`（默认 `0 21 * * 1-5`，`runner.py:81`）。

---

## 3. 同步任务（`sync_jobs.py`）

### 3.1 `sync_all()`（`:317`）

串行管线，合并结果：

```text
sync_stock_list → sync_etf_list → sync_stock_industries → rebuild_search_index
```

每步独立容错：单步失败返回 0 计数，不阻断后续。

### 3.2 `sync_stock_list()`（`:55`）

`AkshareProvider().list_stocks()` → `_to_rows`（补拼音 `make_pinyin_for_search`、分类市场）→ `repo.upsert_stocks`。

市场分类 `_classify_market`（`:15`）：`6`→上证，`0/3`→深证，`8/4`→北交所。

### 3.3 `sync_etf_list()`（`:88`）

同上，`default_type="etf"`。

### 3.4 `sync_stock_industries()`（`:144`）

`list_sectors()` → 逐板块 `get_sector_constituents(name, sector_label=...)` → 构造 `{code, industry}` → `repo.upsert_stock_industries`。逐板块容错。

### 3.5 `rebuild_search_index()`（`:121`）

`repo.load_all_stocks()` → 构造 `StockInfo` 列表 → `get_index().rebuild(items)`。

### 3.6 `sync_market_calendar()`（`:279`）

`ak.tool_trade_date_hist_sina` → `repo.upsert_calendar`（全部标 `is_open=True`）。

### 3.7 `sync_kline(codes=None)`（`:203`）

逐 code 增量同步：

```text
codes 来源：参数 → DB watchlist → SCX_WATCHLIST
逐 code：
  last_date = repo.get_kline_last_date(code)
  if last_date 存在：
    provider.get_kline(code, days=0)  → 过滤 > last_date 的 bar（增量）
  else：
    provider.get_kline(code, days=120)  # 全量初始化
  repo.upsert_klines(rows)
```

---

## 4. 分析任务（`analysis_job.py`）

### 4.1 `daily_analysis_job()`（`:164`）

交易日门控：`repo.is_trading_day()` 返回 False → 跳过，返回 `{"skipped": True}`。否则 `run_daily_analysis(dry_run=False)`。

### 4.2 `run_daily_analysis(dry_run=False, codes=None)`（`:90`）

```text
1. target_codes：参数 → repo.list_watchlist_codes() → SCX_WATCHLIST
   空则返回 0
2. days = SCX_ANALYSIS_KLINE_DAYS（120）
3. name_map = _resolve_names(codes)（DB 查名，空兜底）
4. 逐 code：_analyze_one(provider, code, days, name)
5. repo.upsert_analysis_reports(reports)  # 即使 dry_run 也落库（跳过 trade_date None）
6. 非 dry_run：
   - 读 notify_emails（动态配置）
   - 有报告且有收件人 → render_daily_report → send_email（全部失败也发，避免静默无邮件）
7. 返回 {analyzed, success, failed, sent, reports, elapsed}
```

### 4.3 `_analyze_one()`（`:22`）

```text
1. repo.load_kline(code, days)  → bars
   used_db = len(bars) >= 30
2. 若 DB 不足：
   - provider.get_kline(code, days=days)
   - 异常 → 返回 ok=False
   - 否则 repo.upsert_klines 回填 DB（容错）
3. report = analyze(kline)
4. report = await interpret(report)  # LLM，自动降级
```

---

## 5. TaskManager（`task_manager.py`）

内存级异步任务管理，供 `/admin/sync` 全量同步使用。

- `submit(name, coro_factory)`（`:72`）：生成毫秒时间戳 task_id，`asyncio.create_task`
- 状态：`PENDING → RUNNING → DONE | FAILED`
- `TaskHandle.update_progress` 报告进度（如"正在同步 ETF 列表..."）
- `get(task_id)`（`:122`）：PENDING/RUNNING 实时计算 elapsed
- `list_tasks()`：按时间倒序

> 单进程内存，不跨进程持久。详见 [健康检查与运维接口](../05-api/health-admin.md)。

---

## Related

- [分析引擎](analysis-engine.md)
- [数据模型](../06-data/data-model.md)
- [持久化策略](../06-data/storage.md)
- [运维接口](../05-api/health-admin.md)
