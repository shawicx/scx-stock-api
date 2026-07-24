# 架构设计文档

> 项目：scx-stock-api（股票行情 / AI 分析后端）
> 技术栈：Python 3.13 + uv + FastAPI + AkShare + Redis + APScheduler
> 状态：设计稿（待实现）

---

## 1. 设计目标

提供一个统一的股票行情中台后端，满足以下需求：

1. 查看当天股市信息（板块涨跌、个股涨跌、主力资金）
2. 数据源可配置、可切换
3. 支持多市场（上证、深证、创业板、科创板、北交所、港股、美股、指数）
4. 代码 / 简称 / 拼音搜索股票与 ETF
5. 接入大模型，对 ETF / 个股 / 板块 / 大盘做 AI 分析

---

## 2. 分层总览

```text
┌─────────────────────────────────────────────────────────────┐
│ API Layer         参数校验 → 调 Service → 返回 JSON           │
├─────────────────────────────────────────────────────────────┤
│ Service Layer     业务编排：聚合多个 domain，不感知数据源       │
├─────────────────────────────────────────────────────────────┤
│ Repository Layer  ★ 选源 / 熔断 / 降级 / 缓存命中判断           │
├─────────────────────────────────────────────────────────────┤
│ Provider Layer    按领域接口实现：AkShare / EastMoney / ...    │
├─────────────────────────────────────────────────────────────┤
│ Source            AkShare、东方财富、Yahoo、Alpha Vantage ...   │
└─────────────────────────────────────────────────────────────┘

旁路：
  Storage（DB）   ← 慢变数据落库（K 线 / 列表 / 财务）
  Cache（Redis）  ← 快变数据短 TTL（行情 / 板块 / 资金流）
  Scheduler       ← 定时预热，写入 Storage / Cache
  Search Index    ← 定时全量构建，毫秒级检索
  LLM Client      ← Function Calling，模型自主决定何时拉数据
```

### 各层职责

| 层 | 职责 | 不允许做的事 |
|----|------|------------|
| API | 参数校验、调用 Service、返回 JSON | 不含业务逻辑、不直接调 Provider |
| Service | 业务编排、聚合多 domain | 不感知数据源存在、不写 SQL |
| Repository | 选源、熔断、降级、缓存命中判断 | 不做业务聚合 |
| Provider | 调用具体数据源、做 async 包装 | 不做选源、不做缓存策略 |
| Storage | ORM、DB 读写 | 不调外部数据源 |
| Cache | key 规则、TTL、缓存装饰器 | 不做业务判断 |

---

## 3. 目录结构

```text
backend/
├── scx_stock/                      # 主包（避免 app 包名冲突）
│   ├── api/                        # API 层
│   │   ├── v1/
│   │   │   ├── market.py           # 大盘 / 指数
│   │   │   ├── stock.py            # 个股
│   │   │   ├── etf.py              # ETF
│   │   │   ├── sector.py           # 板块
│   │   │   ├── search.py           # 搜索
│   │   │   ├── fund_flow.py        # 主力资金
│   │   │   └── ai.py               # AI 分析
│   │   ├── deps.py                 # 依赖注入（Repository / Cache → Service）
│   │   ├── errors.py               # 异常 → HTTP 统一转换
│   │   └── router.py
│   │
│   ├── service/                    # 业务编排层
│   │   ├── market_service.py
│   │   ├── stock_service.py
│   │   ├── etf_service.py
│   │   ├── sector_service.py
│   │   ├── search_service.py
│   │   ├── fund_flow_service.py
│   │   └── ai_service.py
│   │
│   ├── repository/                 # ★ 选源 / 熔断 / 降级 / 缓存编排
│   │   ├── router.py               # 按 (domain, market) 路由到 provider
│   │   ├── fallback.py             # 主备切换、failover
│   │   └── base.py
│   │
│   ├── provider/                   # 数据源抽象（按领域拆接口）
│   │   ├── contracts.py            # StockProvider / EtfProvider / ... 接口定义
│   │   ├── base.py                 # 强制 to_thread 包装同步库
│   │   ├── akshare_provider.py
│   │   ├── eastmoney_provider.py
│   │   ├── tushare_provider.py
│   │   ├── yahoo_provider.py
│   │   └── alpha_vantage_provider.py
│   │
│   ├── storage/                    # 持久化层（慢变数据落库）
│   │   ├── db.py
│   │   ├── models.py               # ORM：股票/ETF 列表、K 线、财务
│   │   └── repo.py
│   │
│   ├── search/                     # 搜索索引构建
│   │   ├── index.py                # Trie / 倒排，定时构建
│   │   └── pinyin.py
│   │
│   ├── llm/
│   │   ├── client.py               # 多模型切换
│   │   ├── prompt.py
│   │   ├── analyzer.py             # 编排对话、决定何时调 tool
│   │   └── tools.py                # 把 Provider 能力包成 tool schema
│   │
│   ├── cache/
│   │   ├── backend.py              # redis / memory 后端
│   │   ├── decorators.py           # @cached(ttl=60) 策略载体
│   │   └── keys.py                 # key 命名规则集中
│   │
│   ├── schema/                     # Pydantic 请求 / 响应结构（避免 model 命名歧义）
│   │   ├── market.py
│   │   ├── stock.py
│   │   ├── etf.py
│   │   ├── sector.py
│   │   └── ai.py
│   │
│   ├── exceptions/                 # 异常分层
│   │   ├── provider.py             # ProviderError（超时 / 限流 / 源不可用）
│   │   └── service.py              # ServiceError（代码不存在 / 数据缺失）
│   │
│   ├── middleware/                 # 日志 / 限流 / 耗时
│   │   ├── logging.py
│   │   └── ratelimit.py
│   │
│   ├── scheduler/                  # 后台定时同步
│   │   ├── market_sync.py
│   │   ├── fund_flow_sync.py
│   │   └── search_index_sync.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   └── datasource.py           # 主备源、能力声明（supports）
│   │
│   └── main.py
│
├── tests/
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## 4. 关键工程约束（动工前必须钉死）

### 4.1 AkShare 同步库必须 async 包装

AkShare 内部使用同步 `requests`，在 FastAPI async 环境中直接调用会阻塞整个事件循环。
所有 Provider 必须继承统一基类，对外暴露 `async def`，内部走线程池。

```python
# scx_stock/provider/base.py
from anyio import to_thread


class SyncProviderBase:
    """同步数据源基类，强制走线程池，对外暴露 async。"""

    async def _run(self, func, *args, **kwargs):
        return await to_thread.run_sync(lambda: func(*args, **kwargs))
```

### 4.2 持久化策略表

| 数据 | 变化速度 | 存储 | TTL / 更新 |
|------|---------|------|-----------|
| 实时行情（价格 / 涨跌） | 秒级 | Redis | 30~60s |
| 板块涨跌 | 分钟级 | Redis | 1~5min |
| 主力资金流 | 分钟级 | Redis | 1~5min |
| 搜索结果 | 分钟级 | Redis | 5min |
| 股票 / ETF 列表 | 日级 | **DB + Redis** | 每日 09:00 同步 |
| 历史 K 线 | 日级（收盘后） | **DB** | 收盘后增量 |
| 财务数据 | 季度级 | **DB** | 季报后同步 |

### 4.3 异常分层

```text
ProviderError（超时 / 限流 / 源不可用）  ─┐
                                          ├─→ FastAPI exception_handler → JSON
ServiceError（代码不存在 / 数据缺失）     ─┘
```

Provider 抛 `ProviderError`，Service 转译为 `ServiceError`，API 层 `errors.py` 统一映射为 HTTP 状态码与 JSON 响应。

### 4.4 数据流（读写分离）

读路径：
```text
API → Service → 查 Redis（命中返回）
                 未命中 → Repository → Provider → 写 Redis → 返回
```

写路径（Scheduler 预热）：
```text
Scheduler → Service → Provider → 写 Storage(DB) / Cache(Redis)
```

---

## 5. Provider 接口设计（按领域拆分）

原设计把所有方法塞进单一 `MarketProvider`，导致 Yahoo / Alpha Vantage 等只能 `raise NotImplementedError`。
按领域拆接口，每个 Provider 只实现自己能做的领域。

### 5.1 领域接口

```python
# scx_stock/provider/contracts.py
class StockProvider(Protocol):
    async def get_stock(self, code: str) -> StockInfo: ...
    async def get_stock_quote(self, code: str) -> Quote: ...

class EtfProvider(Protocol):
    async def get_etf(self, code: str) -> EtfInfo: ...

class SectorProvider(Protocol):
    async def get_sector_list(self) -> list[SectorInfo]: ...
    async def get_sector(self, code: str) -> SectorDetail: ...

class FundFlowProvider(Protocol):
    async def get_fund_flow(self, code: str) -> FundFlow: ...
    async def get_market_fund_flow(self) -> MarketFundFlow: ...

class IndexProvider(Protocol):
    async def get_index(self, code: str) -> IndexQuote: ...

class SearchProvider(Protocol):
    async def search(self, keyword: str) -> list[SearchResult]: ...
```

### 5.2 能力声明

```python
# scx_stock/config/datasource.py
akshare_supports = supports(
    markets=["A股", "港股", "指数"],
    domains=["stock", "etf", "sector", "fund_flow", "index"],
)

yahoo_supports = supports(
    markets=["美股", "港股", "指数"],
    domains=["stock", "etf", "index"],
)

alpha_vantage_supports = supports(
    markets=["美股", "外汇"],
    domains=["stock", "forex"],
)
```

### 5.3 Repository 路由

`router.py` 按 `(market, domain)` 选主源；主源失败由 `fallback.py` 切备源。

```text
请求 (domain=stock, market=美股, code=AAPL)
  ↓
router 查能力表 → 主源 Yahoo
  ↓
Yahoo 超时 → fallback → Alpha Vantage
  ↓
返回结果
```

---

## 6. 数据源清单

### 6.1 主备选择

| 数据 | 首选 | 备用 |
|------|------|------|
| A 股行情 | AkShare | 东方财富 |
| ETF | AkShare | 东方财富 |
| 板块 | AkShare | 东方财富 |
| 主力资金 | AkShare | 东方财富 |
| 财务数据 | AkShare | TuShare（Pro） |
| 美股 | Yahoo Finance | Alpha Vantage / Finnhub |
| 港股 | AkShare | Yahoo Finance |
| 外汇 | Alpha Vantage | Twelve Data |
| 指数 | AkShare | Yahoo Finance |

### 6.2 公开数据源能力对比

| 数据源 | A 股 | ETF | 港股 | 美股 | 指数 | 外汇 | 费用 | 接入方式 |
|--------|------|-----|------|------|------|------|------|---------|
| **AkShare** | ✅ | ✅ | ✅ | ✅ | ✅ | 部分 | 免费 | Python 库（首选） |
| **东方财富** | ✅ | ✅ | ✅ | 部分 | ✅ | ✗ | 免费（非官方接口） | HTTP |
| 新浪财经 | ✅ | ✅ | ✅ | 部分 | ✅ | ✗ | 免费（非官方接口） | HTTP |
| 腾讯财经 | ✅ | ✅ | ✅ | 部分 | ✅ | ✗ | 免费（非官方接口） | HTTP |
| **TuShare** | ✅ | ✅ | 部分 | ✗ | ✅ | ✗ | 基础免费 / Pro 积分 | Token |
| **Yahoo Finance** | 部分 | ✅ | ✅ | ✅ | ✅ | ✅ | 免费（非官方接口） | `yfinance` 库 |
| **Alpha Vantage** | 部分 | ETF | ✅ | ✅ | ✅ | ✅ | 25 次/天免费 + 付费 | API Key |
| Finnhub | 部分 | ✅ | ✅ | ✅ | ✅ | ✗ | 60 次/分免费 + 付费 | API Key |
| Twelve Data | 部分 | ✅ | ✅ | ✅ | ✅ | ✅ | 800 次/天免费 | API Key |
| Polygon.io | ✗ | ✅ | ✅ | ✅ | ✅ | ✗ | 免费额度小 + 付费 | API Key |
| FMP | ✗ | ✅ | ✅ | ✅ | ✅ | ✗ | 250 次/天免费 | API Key |

### 6.3 限速与稳定性约束

- A 股实时行情：AkShare 底层抓东方财富 / 新浪，**高频会被封 IP**。
  必须靠 Redis 缓存 + Scheduler 预热，前端永远打缓存。
- 美股源（Yahoo / Alpha Vantage）：国内访问不稳定，**生产建议配代理或选 Finnhub**。
- 限速型数据源（Alpha Vantage 25 次/天）：只作为 fallback，不作为主源。

---

## 7. 多市场支持

| 市场 | 代码示例 | 主源 | 备源 |
|------|---------|------|------|
| 上证 | 600519、510300 | AkShare | 东方财富 |
| 深证 | 000001、159915 | AkShare | 东方财富 |
| 创业板 | 300750 | AkShare | 东方财富 |
| 科创板 | 688981 | AkShare | 东方财富 |
| 北交所 | 830799 | AkShare（部分接口） | 东方财富 |
| 港股 | 00700 | AkShare | Yahoo |
| 美股（NASDAQ / NYSE） | AAPL、MSFT | Yahoo | Alpha Vantage / Finnhub |
| 纳斯达克指数 | ^IXIC | Yahoo | AkShare |
| 标普 500 | ^GSPC | Yahoo | AkShare |
| 道琼斯 | ^DJI | Yahoo | AkShare |
| 恒生指数 | ^HSI | AkShare | Yahoo |

市场识别规则（Repository 层）：
- A 股：代码以 `6 / 0 / 3 / 8` 开头（纯数字，6 位或 5 位北交所）
- 港股：纯数字（通常 4~5 位）
- 美股：字母代码（1~5 个字母）

---

## 8. 搜索设计

现拉现搜不现实（多数数据源无像样的模糊搜索）。采用"定时全量拉取 + 自建索引"。

### 8.1 流程

```text
Scheduler 每日 09:00 拉全量股票 / ETF 列表 → 写 Storage(DB)
  ↓
search/index.py 构建 Trie / 倒排索引（代码、简称、拼音首字母）
  ↓
索引放内存 + Redis（便于多实例共享）
  ↓
搜索走索引，毫秒级返回
```

### 8.2 支持的匹配维度

- 精确代码：`510300` → 沪深 300ETF
- 简称：`贵州茅台` → 600519
- 拼音首字母：`gzmt` → 600519 贵州茅台

---

## 9. AI 分析设计

### 9.1 流程（Function Calling）

```text
用户问题
  ↓
analyzer → LLM（决定是否需要调 tool）
  ↓
tools（查行情 / 资金流 / K 线）→ Provider 拉实时数据
  ↓
结果回填 LLM
  ↓
生成分析 → 返回前端
```

关键：模型自主决定何时反向拉数据，而非一次性塞死 Prompt。

### 9.2 模块职责

| 模块 | 职责 |
|------|------|
| `llm/client.py` | 统一接口，切换 OpenAI / DeepSeek / Qwen / Claude / Gemini |
| `llm/prompt.py` | 系统提示词、角色设定 |
| `llm/tools.py` | 把 Provider 能力包成 Function Calling tool schema |
| `llm/analyzer.py` | 编排对话、决定何时调 tool、汇总结果 |

### 9.3 支持的模型

OpenAI / DeepSeek / Qwen / Claude / Gemini，切换仅需替换 client。

### 9.4 成本与限流

AI 接口昂贵，必须：
- `middleware/ratelimit.py` 按 用户 / IP 限流
- 每次调用记录 token 消耗与成本

---

## 10. API 设计

### 10.1 市场

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/market/index` | 大盘指数（上证、深证、创业板、恒生、纳斯达克...） |

### 10.2 板块

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sector/list` | 板块涨跌排行 |
| GET | `/sector/{code}` | 板块详情（涨跌幅、成交额、领涨股、资金流） |

### 10.3 个股

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stock/{code}` | 个股详情（基本信息、实时行情、K 线、资金流、所属板块） |

### 10.4 ETF

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/etf/{code}` | ETF 详情（行情、规模、跟踪指数、折溢价、资金流） |

### 10.5 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/search?q={keyword}` | 跨股票 / ETF / 指数搜索（代码 / 简称 / 拼音） |

### 10.6 主力资金

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/fund_flow/{code}` | 个股 / ETF 主力资金 |
| GET | `/fund_flow/market` | 大盘资金流 |

### 10.7 AI

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/ai/analyze` | AI 分析（股票 / ETF / 板块 / 大盘 / 问答） |

请求体示例：
```json
{
  "type": "stock",
  "code": "600519",
  "question": "最近走势怎么样？"
}
```

---

## 11. 需求覆盖矩阵

| 需求 | 能否实现 | 关键依赖 |
|------|---------|---------|
| 当天行情（板块 / 个股 / 资金） | ✅ | Redis 缓存 + Scheduler 预热（绕过限速） |
| 数据源可选 | ✅ | Repository 路由 + Provider 能力声明 |
| 上证 / 深证 / 纳斯达克等 | ✅ | 跨市场路由；美股需注意国内访问稳定性 |
| 代码 / 名称搜索 | ✅ | 自建搜索索引（定时全量拉取） |
| AI 分析 | ✅ | Function Calling + 限流控成本 |

### 上线前必须解决的硬约束

1. **AkShare 同步库必须 `to_thread` 包装**（否则阻塞事件循环）
2. **实时行情必须 Redis 缓存兜底**（否则被源限速 / 封 IP）
3. **美股源国内访问需配代理**（否则不稳定）

---

## 12. 待定事项（实现时再决策）

- [ ] 数据库选型：SQLite（开发） vs PostgreSQL（生产）
- [ ] 搜索引擎：自建 Trie / 倒排 vs Whoosh vs Redisearch
- [ ] LLM 默认模型
- [ ] 限流策略：内存令牌桶 vs Redis
- [ ] 部署方式：单进程 vs Docker
