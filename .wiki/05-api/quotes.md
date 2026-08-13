# 行情与搜索接口

> 股票/ETF 行情列表、个股详情、搜索。

源码：`scx_stock/api/v1/stock.py`、`scx_stock/api/v1/search.py`、`scx_stock/schema/stock.py`。需认证。

---

## 1. `GET /api/v1/stock/list` — 行情列表

| 参数 | 位置 | 默认 | 约束 | 说明 |
|------|------|------|------|------|
| `market` | query | `全部` | `^(上证\|深证\|创业板\|科创板\|北交所\|全部)$` | 市场板块 |
| `type` | query | `stock` | `^(stock\|etf\|all)$` | 证券类型 |
| `sort_by` | query | `change_pct` | `^(change_pct\|amount\|turnover_rate\|main_net_inflow)$` | 排序字段 |
| `descending` | query | `true` | bool | 是否降序 |
| `page` | query | `1` | `ge=1` | 页码 |
| `page_size` | query | `20` | `ge=1, le=100` | 每页条数 |

**响应 `data`**：`{items: list[StockListItem], total, page, page_size}`

`StockListItem` 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | str | 代码 |
| `name` | str | 简称 |
| `market` | str | 市场 |
| `price` | float\|null | 最新价 |
| `change` | float\|null | 涨跌额 |
| `change_pct` | float\|null | 涨跌幅 |
| `amount` | float\|null | 成交额 |
| `volume` | float\|null | 成交量 |
| `turnover_rate` | float\|null | 换手率 |
| `high` / `low` / `open` / `prev_close` | float\|null | 高/低/开/前收 |
| `main_net_inflow` | float\|null | 主力净流入（元） |
| `main_net_inflow_pct` | float\|null | 主力净流入占比 |
| `industry` | str\|null | 行业 |

> - `main_net_inflow` / `main_net_inflow_pct` / `industry` / `turnover_rate` 等可能为 `null`（取决于命中的数据源）
> - **数据源字段差异**：东方财富字段最全；新浪缺换手率/主力资金；腾讯含换手率+主力资金但缺高低价
> - 行情列表缓存 120s

---

## 2. `GET /api/v1/stock/{code}` — 个股详情

| 参数 | 位置 | 说明 |
|------|------|------|
| `code` | path | A 股代码，正则 `^[0368]\d{4,5}$`（非法 → 400 `code:40001`） |

**响应 `data`**（`StockDetailResponse.to_dict()`）：

```json
{
  "info": { "code": "600519", "name": "贵州茅台", "market": "上证", "industry": "白酒" },
  "quote": {
    "code": "600519", "name": "贵州茅台",
    "price": 1800.0, "prev_close": 1790.0,
    "change": 10.0, "change_pct": 0.56,
    "volume": 123456, "amount": 1000000,
    "high": 1810.0, "low": 1785.0, "open": 1795.0,
    "timestamp": "2026-08-09T10:00:00"
  },
  "fetched_at": "2026-08-09T10:00:00"
}
```

> 仅支持 A 股个股代码（首位 0/3/6/8）。ETF 详情暂不支持。

---

## 3. `GET /api/v1/search` — 搜索

| 参数 | 位置 | 默认 | 约束 | 说明 |
|------|------|------|------|------|
| `q` | query | 必填 | `min_length=1` | 关键词（代码/简称/拼音） |
| `limit` | query | `20` | `ge=1, le=100` | 最大返回数 |

**响应 `data`**（按相关度降序）：

```json
[
  { "code": "600519", "name": "贵州茅台", "market": "上证", "type": "stock", "score": 100 }
]
```

**评分**（`search/index.py:144`，首匹配优先）：

| 匹配 | 分数 |
|------|:----:|
| 代码精确 | 100 |
| 代码前缀 | 80 |
| 简称精确 | 60 |
| 简称前缀 | 50 |
| 简称包含 | 40 |
| 拼音全拼前缀 | 30 |
| 拼音首字母前缀 | 20 |

> 索引由调度任务每日 09:20 构建。索引为空时返回 `[]`，可调 `POST /admin/reindex` 手动重建。

---

## 4. `GET /api/v1/search/index-size` — 索引大小

无参数。

**响应 `data`**：`{size: int}`

---

## Related

- [API 总览](overview.md)
- [板块/指数/黄金](sectors-indexes-gold.md)
- [前端联调](../09-frontend-integration/frontend-guide.md)
- [缓存策略](../04-data-providers/cache.md)
