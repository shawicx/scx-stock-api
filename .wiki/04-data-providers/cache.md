# 缓存策略

> Redis/内存双实现缓存、键命名、各 Repository TTL。

源码：`scx_stock/cache/backend.py`、`scx_stock/cache/keys.py`、`scx_stock/repository/*.py`。

---

## 1. CacheBackend 抽象（`cache/backend.py`）

```python
class CacheBackend:
    async def get(self, key) -> Any           # 反序列化或 None
    async def set(self, key, value, ttl)      # ttl 秒
    async def incr(self, key, ttl) -> int     # 原子计数（限流用）
    async def close()
```

### RedisCache（`backend.py:50`）

- `get`：`client.get(key)` → `json.loads`
- `set`：`client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)`
- `incr`：pipeline `INCR` + `EXPIRE`（每次都刷新 TTL）
- `close`：`client.aclose()`

### MemoryCache（`backend.py:82`）

- 内存字典 `dict[str, tuple[value, expire_at]]`
- `get`：惰性删除过期项
- `incr`：不存在/过期则重置为 `(1, now+ttl)`；存在则计数（**不刷新** TTL，与 RedisCache 行为略有差异）
- `close`：清空字典

### get_cache 单例（`backend.py:125`）

模块级 `_cache` 单例。尝试 `aioredis.from_url(...)`（`socket_connect_timeout=2`，`ping()`），失败回退 `MemoryCache()`。Redis URL 由 `settings.redis_*` 构建。

---

## 2. 缓存键命名（`cache/keys.py`）

前缀 `PREFIX = "scx"`。

| 函数 | 键 | 用途 |
|------|-----|------|
| `stock_quote(code)` | `scx:stock:quote:{code}` | 个股行情 |
| `stock_list()` | `scx:stock:list` | （保留） |
| `stock_quote_list(market)` | `scx:stock:quote-list:{market}` | 行情列表 |
| `etf_quote_list()` | `scx:etf:quote-list` | ETF 行情列表 |
| `search_result(keyword)` | `scx:search:{keyword}` | 搜索结果 |
| `sector_list()` | `scx:sector:list` | 板块列表 |
| `sector_detail(name)` | `scx:sector:detail:{name}` | 板块详情 |
| `index_list(group)` | `scx:index:list:{group}` | 指数列表 |
| `gold_quotes()` | `scx:gold:quotes` | 黄金行情 |
| `rate_limit(scope, identity)` | `scx:ratelimit:{scope}:{identity}` | 限流计数 |

> **已知不一致**：`StockRepository.get_stock`（`repository/router.py:74`）用 ad-hoc 键 `f"stock:info:{code}"`，缺 `scx:` 前缀。其余键均走 `keys.py`。

---

## 3. 各 Repository TTL

| Repository | 方法 | TTL（秒） | 键 |
|-----------|------|:---------:|-----|
| StockRepository | `get_stock` | 300 | `stock:info:{code}` |
| StockRepository | `get_quote` | 30 | `stock:quote:{code}` |
| StockRepository | `list_stock_quotes` | 120 | `stock:quote-list:全部` |
| StockRepository | `list_etf_quotes` | 120 | `etf:quote-list` |
| SectorRepository | `list_sectors` | 120 | `sector:list` |
| SectorRepository | `get_sector_detail` | 120 | `sector:detail:{name}` |
| IndexRepository | `list_indexes` | 120 | `index:list:{group}` |
| GoldRepository | `list_gold_quotes` | 120 | `gold:quotes` |

> `IndexRepository.list_major_indexes` 无独立缓存，复用 `list_indexes` 后白名单过滤。

---

## 4. 持久化策略总览

| 数据 | 变化速度 | 存储 | TTL |
|------|---------|------|-----|
| 实时行情（个股） | 秒级 | Redis | 30s |
| 个股基础信息 | 分钟级 | Redis | 300s |
| 行情列表 / ETF | 秒~分钟级 | Redis | 120s |
| 板块 / 指数 / 黄金 | 分钟级 | Redis | 120s |
| 搜索结果 | 分钟级 | Redis | 60s |
| 股票/ETF 列表 | 日级 | DB + Redis | 每日 09:00 同步 |
| 行业映射 | 日级 | DB | 每日 09:15 同步 |
| K 线 | 日级 | DB | 每日 16:00 增量同步 |
| 分析报告 | 日级 | DB | 每日 21:00 落库 |

DB 细节见 [06-data](../06-data/storage.md)。

---

## Related

- [多源 Fallback](fallback.md)
- [Provider 契约](contracts.md)
- [数据模型](../06-data/data-model.md)
- [限流设计](../05-api/overview.md)
