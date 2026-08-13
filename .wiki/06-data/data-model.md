# 数据模型

> 8 张 ORM 表的字段、类型、约束、索引。

源码：`scx_stock/storage/models.py`。所有表继承 `Base`（`storage/db.py:21`），使用 PostgreSQL `JSONB`，时间戳为 `DateTime(timezone=True)`。

---

## 1. 表清单

| 表名 | 模型类 | 主键 | 用途 |
|------|--------|------|------|
| `stock` | `StockModel` | 复合 (code, type) | 股票/ETF 基础信息 |
| `kline` | `KlineModel` | id | 历史 K 线 |
| `market_calendar` | `MarketCalendarModel` | trade_date | 交易日历 |
| `stock_industry` | `StockIndustryModel` | code | 行业映射 |
| `app_setting` | `AppSettingModel` | key | 应用配置（KV） |
| `watchlist` | `WatchlistModel` | code | 关注列表 |
| `analysis_report` | `AnalysisReportModel` | id | 分析报告历史 |
| `auth_code` | `AuthCodeModel` | code | 访问授权码 |

---

## 2. 详细字段

### `stock`（`models.py:14`）

| 字段 | 类型 | 约束/索引 | 说明 |
|------|------|----------|------|
| `code` | String(16) | PK（复合） | 代码 |
| `type` | String(16) | PK（复合） | stock / etf |
| `name` | String(64) | 索引 | 简称 |
| `market` | String(16) | 索引 | 上证/深证/创业板/科创板/北交所 |
| `pinyin` | String(128) | 索引，nullable | `"full\|initials"` |
| `updated_at` | DateTime(tz) | server_default now, onupdate now | |

唯一约束 `uq_stock_code_type (code, type)`。Scheduler 每日 09:00 同步。

---

### `kline`（`models.py:33`）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, autoincrement | |
| `code` | String(16) | 索引 | 代码 |
| `trade_date` | Date | 索引 | 交易日 |
| `open` / `close` / `high` / `low` / `volume` | Float | | OHLCV |
| `updated_at` | DateTime(tz) | | |

唯一约束 `uq_kline_code_date (code, trade_date)`。`sync_kline` 每日 16:00 增量同步。

---

### `market_calendar`（`models.py:57`）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `trade_date` | Date | PK | 交易日 |
| `is_open` | Boolean | default True | 是否开市 |

每周一 06:00 同步（`ak.tool_trade_date_hist_sina`，约 8797 行）。

---

### `stock_industry`（`models.py:70`）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `code` | String(16) | PK | 代码 |
| `industry` | String(64) | | 行业名 |
| `updated_at` | DateTime(tz) | | |

Scheduler 每日 09:15 同步（板块成分股反查）。

---

### `app_setting`（`models.py:86`）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `key` | String(64) | PK | 配置键 |
| `value` | String(512) | | 配置值 |
| `updated_at` | DateTime(tz) | | |

前端 `/settings` 页管理。动态配置详见 [dynamic-config](../08-configuration/dynamic-config.md)。

---

### `watchlist`（`models.py:102`）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `code` | String(16) | PK | 代码 |
| `name` | String(64) | default "" | 简称 |
| `sort_order` | Integer | default 0 | 排序 |
| `created_at` | DateTime(tz) | server_default now | |

前端 `/watchlist` CRUD。每日分析任务的目标来源。

---

### `analysis_report`（`models.py:119`）

| 字段 | 类型 | 约束/索引 | 说明 |
|------|------|----------|------|
| `id` | Integer | PK, autoincrement | |
| `code` | String(16) | 索引 | 代码 |
| `trade_date` | Date | 索引 | 交易日 |
| `name` | String(64) | default "" | 简称 |
| `close` | Float | nullable | 收盘价 |
| `change_pct` | Float | nullable | 涨跌幅 |
| `trend` | String(16) | default "", 索引 | 趋势 |
| `ok` | Boolean | default True | 是否成功 |
| `payload` | JSONB | | 完整报告（含支撑/压力/MA/summary） |
| `updated_at` | DateTime(tz) | | |

唯一约束 `uq_report_code_date (code, trade_date)`。每日分析后落库。

---

### `auth_code`（`models.py:146`）

| 字段 | 类型 | 约束/索引 | 说明 |
|------|------|----------|------|
| `code` | String(16) | PK | 授权码 |
| `is_active` | Boolean | default True, 索引 | 是否有效 |
| `expires_at` | DateTime(tz) | | 过期时间 |
| `created_at` | DateTime(tz) | server_default now | |

认证机制详见 [auth.md](../05-api/auth.md)。

---

## Related

- [持久化与存储](storage.md)
- [缓存策略](../04-data-providers/cache.md)
- [认证机制](../05-api/auth.md)
- [应用配置](../05-api/settings.md)
