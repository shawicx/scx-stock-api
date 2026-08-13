# 板块、指数、黄金接口

> 板块涨跌排行与详情、大盘指数、黄金行情。需认证。

源码：`scx_stock/api/v1/sector.py`、`market.py`、`gold.py`，对应 `schema/sector.py`、`schema/index.py`、`schema/gold.py`。

---

## 1. 板块

### `GET /api/v1/sector/list` — 板块涨跌排行

| 参数 | 位置 | 默认 | 约束 | 说明 |
|------|------|------|------|------|
| `sort_by` | query | `change_pct` | — | change_pct / turnover_rate / total_market_cap |
| `descending` | query | `true` | bool | 是否降序 |
| `limit` | query | `50` | `ge=1, le=200` | 最大返回数 |

**响应 `data`**：`list[SectorQuote]`

`SectorQuote` 字段：`code, name, label, price, change, change_pct, total_market_cap, turnover_rate, up_count, down_count, leading_stock, leading_stock_change_pct`（多数可 null）。

### `GET /api/v1/sector/{name}` — 板块详情

| 参数 | 位置 | 说明 |
|------|------|------|
| `name` | path | 板块名称（如 `白酒`、`小金属`） |

**响应 `data`**（`SectorDetail`）：

```json
{
  "quote": { ... },
  "constituents": [
    { "code": "600519", "name": "贵州茅台" },
    { "code": "000858", "name": "五粮液" }
  ]
}
```

> 缓存 120s。成分股仅东方财富源（Repository 调用不传 `sector_label`）。

---

## 2. 大盘指数

### `GET /api/v1/market/index` — 主要指数（白名单 8 个）

无参数。返回白名单过滤后的主要指数。

白名单（`repository/index_repo.py:21` `MAJOR_INDEX_CODES`）：

| 代码 | 名称 |
|------|------|
| 000001 | 上证指数 |
| 399001 | 深证成指 |
| 399006 | 创业板指 |
| 000688 | 科创50 |
| 899050 | 北证50 |
| 000300 | 沪深300 |
| 000905 | 中证500 |
| 000852 | 中证1000 |

### `GET /api/v1/market/index/all` — 全部指数（按分组）

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `group` | query | `沪深重要指数` | 沪深重要指数/上证系列指数/深证系列指数/指数成份/中证系列指数 |

**响应 `data`**（两接口通用）：`list[IndexQuote]`

`IndexQuote` 字段：`code, name, price, change_pct, change, volume, amount, amplitude, high, low, open, prev_close`（多数可 null）。

> 缓存 120s。

---

## 3. 黄金

### `GET /api/v1/market/gold` — 黄金品种实时行情

无参数。

**响应 `data`**：`list[GoldQuote]`（最多 3 条）

`GoldQuote` 字段：`code, name, category, price, change, change_pct, prev_close, prev_settlement, open, high, low, volume, position, timestamp`（多数可 null）。

| 品种 | 来源 |
|------|------|
| AU0（沪金主连） | `futures_zh_realtime` |
| Au99.99 | `spot_quotations_sge` |
| NYAuTN06（纽约金） | `spot_hist_sge` |

> 缓存 120s。单品种失败不影响其他，最多返回 3 条。

---

## Related

- [API 总览](overview.md)
- [行情与搜索](quotes.md)
- [多源 Fallback](../04-data-providers/fallback.md)
