# 多源 Fallback 机制

> AkShare 多数据源自动切换机制。**核心难点**：东方财富在阿里云 ECS 被反爬封锁，需多源 fallback 保可用。

源码：`scx_stock/provider/akshare_provider.py`、`scx_stock/provider/base.py`。

---

## 1. `_call_with_fallback` 工作原理

`AkshareProvider._call_with_fallback(sources, domain, validate=None)`（`akshare_provider.py:36`）按优先级尝试多个数据源函数，第一个成功就返回 `(源名, DataFrame)`：

```python
sources = [
    ("em",   ak.stock_zh_a_spot_em, {}),    # 东方财富（字段全）
    ("sina", ak.stock_zh_a_spot,    {}),    # 新浪（字段少但云可用）
    ("tx",   ak.stock_zh_a_spot_tx, {}),    # 腾讯（含换手率+主力资金）
]
source, df = await self._call_with_fallback(sources, domain="list_stock_quotes")
```

- 遍历 `sources`，每个源通过 `_run`（推入线程池）执行
- 若提供 `validate` 回调且返回 `False`，视为失败继续 fallback（防御空 DataFrame / 列名不匹配静默失败）
- 第一个成功的源返回 `(source_name, result)`；`i > 0` 时记 info 日志 "fallback to X succeeded"
- 全部失败抛 `ProviderUnavailableError`

---

## 2. 各方法精确 Fallback 顺序

> **重要**：fallback 顺序因方法而异。提交 `89dfa49 "新浪作为第一源"` **仅修改了 ETF 两个方法**，将新浪提到第一。股票行情/列表仍是东方财富优先。

| 方法 | 第一源 | 第二源 | 第三源 | 备注 |
|------|--------|--------|--------|------|
| `list_stock_quotes` | 东方财富 `stock_zh_a_spot_em` | 新浪 `stock_zh_a_spot` | 腾讯 `stock_zh_a_spot_tx` | 腾讯含主力资金 `zljlr` |
| `get_quote` | 东方财富 `stock_zh_a_spot_em` | 新浪 `stock_zh_a_spot` | 腾讯 `stock_zh_a_spot_tx` | 腾讯代码格式 `sh600519` |
| `list_stocks` | 东方财富 `stock_zh_a_spot_em` | 新浪 `stock_zh_a_spot` | 腾讯 `stock_zh_a_spot_tx` | 搜索索引用 |
| **`list_etfs`** | **新浪 `fund_etf_category_sina`** | 东方财富 `fund_etf_spot_em` | 同花顺 `fund_etf_spot_ths` | **新浪第一**（commit 89dfa49） |
| **`list_etf_quotes`** | **新浪 `fund_etf_category_sina`** | 东方财富 `fund_etf_spot_em` | 同花顺 `fund_etf_spot_ths` | **新浪第一**（commit 89dfa49） |
| `list_sectors` | 东方财富 `stock_board_industry_name_em` | 新浪 `stock_sector_spot` | — | |
| `list_indexes` | 东方财富 `stock_zh_index_spot_em` | 新浪 `stock_zh_index_spot_sina` | — | |
| `get_sector_constituents` | 东方财富 `stock_board_industry_cons_em` | 新浪 `stock_sector_detail`（仅当传 `sector_label`） | — | Repository 调用时不传 label，实际只用东方财富 |
| `get_kline`（ETF） | 东方财富 `fund_etf_hist_em` | 新浪 `fund_etf_hist_sina` | — | 代码首位 5/1 且 6 位 |
| `get_kline`（股票） | 东方财富 `stock_zh_a_hist` | 腾讯 `stock_zh_a_hist_tx` | — | |
| `get_stock` | 东方财富 `stock_individual_info_em` | — | — | **无 fallback**，单源 |
| `list_gold_quotes` | （3 个品种各自独立 try，非 fallback 链） | | | 见下 |

### 黄金 `list_gold_quotes`（特殊）

不走 `_call_with_fallback`，3 个品种各自独立 try/except，失败返回 `None`：

| 品种 | AkShare 函数 |
|------|-------------|
| AU0（沪金主连） | `ak.futures_zh_realtime(symbol="黄金")` 过滤 `symbol=="AU0"` |
| Au99.99 | `ak.spot_quotations_sge` |
| NYAuTN06（纽约金） | `ak.spot_hist_sge(symbol="NYAuTN06")` |

最多返回 3 条，单品种失败不影响其他。

---

## 3. validate 校验回调

防御"拉到空 DataFrame / 列名不匹配"等静默失败场景。两个工厂函数（`akshare_provider.py:738`、`:750`）：

- `_validate_non_empty_df(df)`：非 None、有 `.empty` 属性、非空
- `_validate_df_with_columns(*cols)`：非空 **且** 包含至少一个候选列名（任一匹配即可）

```python
validate=_validate_df_with_columns("代码", "code")  # 东方财富用"代码"，腾讯用"code"
```

---

## 4. 腾讯源列名映射

腾讯源列名是拼音缩写（与东方财富/新浪的中文列名完全不同），有独立映射逻辑：

| 腾讯列名 | 含义 | 映射到 |
|---------|------|--------|
| `code` | `sh600519` 格式 | 标准代码（去前缀） |
| `name` | 名称 | name |
| `zxj` | 最新价 | price |
| `zdf` | 涨跌幅 | change_pct |
| `zd` | 涨跌额 | change |
| `volume` / `turnover` | 成交量 / 成交额 | volume / amount |
| `hsl` | 换手率 | turnover_rate |
| `zljlr` | 主力净流入（**万元**） | main_net_inflow（× 1e4 转元） |

---

## 5. Provider 层 monkey-patch（`provider/base.py`）

模块加载时对 `requests.Session.request` 打补丁（`base.py:97`），三件事：

### 5.1 注入浏览器 User-Agent

东方财富会拒绝无 UA 的请求。`base.py:80` 在请求未带 `user-agent` 头时注入 Chrome 120 UA（`_USER_AGENT`，`base.py:18`）。

### 5.2 国内数据源绕过代理

`_DIRECT_DOMAINS`（`base.py:24`）覆盖的域名强制 `proxies={"http": None, "https": None}` 直连，避免本地代理（Clash/Surge）SSL 干扰：

- 东方财富 8 个 host（`push2.eastmoney.com` 等）
- 新浪：`hq.sinajs.cn`、`vip.stock.finance.sina.com.cn`、`money.finance.sina.com.cn`、`finance.sina.com.cn`
- 腾讯：`qt.gtimg.cn`、`web.ifzq.gtimg.cn`
- 同花顺：`10jqka.com.cn`
- 上金所：`sge.com.cn`

### 5.3 东方财富超时缩短

`_EM_DOMAINS`（`base.py:47`）匹配的东方财富域名强制 `timeout=5s`（`_EM_TIMEOUT`，`base.py:59`）。AkShare 默认 15s × 3 次重试（最坏 ~50s）太慢，缩短后加速 fallback。

### 5.4 `_run` / to_thread

`SyncProviderBase._run`（`base.py:107`）通过 `anyio.to_thread.run_sync` 将同步 AkShare 调用推入线程池，对外暴露 async 语义。这是所有 Provider 方法的唯一同步→异步 chokepoint。

---

## 6. Repository 层 fallback（当前休眠）

`repository/router.py:148` 的 `_call_with_fallback` 是**第二层 fallback**（Provider 级别），通过 `config/datasource.py` 的 `select_providers(market, domain)` 选择 Provider。当前 `CAPABILITIES` 表中只有 `akshare` 有实际实现，所以这层 fallback 实际休眠。

---

## Related

- [Provider 契约](contracts.md)
- [缓存策略](cache.md)
- [架构分层](../01-overview/architecture.md)
- [代码结构](../03-codebase/codebase.md)
