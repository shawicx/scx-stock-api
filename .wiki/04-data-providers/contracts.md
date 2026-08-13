# Provider 契约

> Provider 层的抽象接口、基类、数据源能力声明。

源码：`scx_stock/provider/contracts.py`、`scx_stock/provider/base.py`、`scx_stock/config/datasource.py`。

---

## 1. Protocol 接口（`contracts.py`）

三个 `@runtime_checkable` Protocol（仅声明，`AkshareProvider` 实现远超这些）：

```python
@runtime_checkable
class StockProvider(Protocol):
    async def get_stock(self, code: str) -> StockInfo: ...
    async def get_quote(self, code: str) -> Quote: ...

@runtime_checkable
class KlineProvider(Protocol):
    async def get_kline(self, code: str, days: int = 120) -> Kline: ...

@runtime_checkable
class IndexProvider(Protocol):
    async def get_index(self, code: str): ...   # 占位，未实现
```

> 注意：`list_stock_quotes` / `list_etfs` / `list_sectors` / `list_indexes` / `list_gold_quotes` 等方法**没有对应的 Protocol**，直接由 `AkshareProvider` 提供。

---

## 2. SyncProviderBase（`base.py:100`）

同步库 Provider 的基类。`AkshareProvider` 继承它（`name = "akshare"`）。

核心方法：

```python
async def _run(self, func, *args, **kwargs):
    """将同步 AkShare 调用推入线程池执行。"""
    return await to_thread.run_sync(lambda: func(*args, **kwargs))
```

模块加载时的 monkey-patch（UA 注入 / 代理绕过 / 东方财富超时）详见 [fallback.md §5](fallback.md)。

---

## 3. 数据源能力声明（`config/datasource.py`）

`CAPABILITIES`（`datasource.py:40`）声明每个数据源支持的市场与领域，供 Repository 层 `select_providers(market, domain)` 路由：

| 数据源 | 市场 | 领域 |
|--------|------|------|
| **akshare** | A股、港股、指数 | stock、etf、sector、fund_flow、index、search（全部） |
| eastmoney | A股、港股 | stock、etf、sector、fund_flow |
| yahoo | 美股、港股、指数 | stock、etf、index |
| alpha_vantage | 美股 | stock、etf |

> **注意**：只有 `akshare` 有实际 Provider 实现（`scx_stock/provider/akshare_provider.py`）。其余三个仅声明能力，无实现。因此 Repository 层的 Provider 级 fallback 当前休眠。

`Market = Literal["A股", "港股", "美股", "指数"]`
`Domain = Literal["stock", "etf", "sector", "fund_flow", "index", "search"]`

`select_providers(market, domain)`（`datasource.py:64`）按声明顺序返回数据源名（主源在前）。

---

## 4. AkshareProvider 关键方法清单

| 方法 | 签名 | 用途 |
|------|------|------|
| `get_stock` | `(code) -> StockInfo` | 个股基础信息（无 fallback） |
| `get_quote` | `(code) -> Quote` | 实时行情 |
| `list_stocks` | `() -> list[StockInfo]` | 全量股票（搜索索引/同步用） |
| `list_stock_quotes` | `() -> list[StockListItem]` | 行情列表（含主力资金） |
| `list_etfs` | `() -> list[StockInfo]` | ETF 列表 |
| `list_etf_quotes` | `() -> list[StockListItem]` | ETF 行情 |
| `list_sectors` | `() -> list[SectorQuote]` | 板块排行 |
| `get_sector_constituents` | `(name, sector_label=None) -> list[dict]` | 板块成分股 |
| `list_indexes` | `(group="沪深重要指数") -> list[IndexQuote]` | 指数列表 |
| `get_kline` | `(code, days=120) -> Kline` | K 线（股票/ETF 分支） |
| `list_gold_quotes` | `() -> list[GoldQuote]` | 黄金行情 |

各方法 fallback 顺序见 [fallback.md §2](fallback.md)。

---

## Related

- [多源 Fallback 详解](fallback.md)
- [缓存策略](cache.md)
- [代码结构](../03-codebase/codebase.md)
