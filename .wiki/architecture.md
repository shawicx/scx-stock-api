# 架构文档

> 项目：scx-stock-api（股票行情后端）
> 状态：**已实现**（本文档基于实际代码，非设计稿）

---

## 1. 项目定位

统一的股票行情中台后端，提供：

- A 股 / ETF 实时行情（价格、涨跌、换手、主力资金）
- 行业板块涨跌排行与详情
- 大盘指数（上证、深证、创业板等）
- 代码 / 简称 / 拼音搜索
- 行业映射（板块成分股反查）

配套前端：[scx-gold](https://github.com/shawicx/scx-gold)（React 涨停候选筛选器）。

---

## 2. 技术栈

| 层面 | 选型 |
|------|------|
| 语言 | Python 3.13+（`requires-python = ">=3.13"`） |
| Web 框架 | FastAPI ≥0.115 + Uvicorn |
| 数据源 | AkShare ≥1.14（东方财富 / 新浪 / 腾讯多源 fallback） |
| ORM | SQLAlchemy 2.0（async）+ asyncpg |
| 数据库 | PostgreSQL 16（开发期自动建库） |
| 缓存 | Redis ≥5.0（无 Redis 时回退内存缓存） |
| 调度 | APScheduler ≥3.10（AsyncIOScheduler） |
| 配置 | pydantic-settings ≥2.0（环境变量 + .env） |
| 拼音 | pypinyin ≥0.51 |
| 包管理 | uv（锁文件 `uv.lock`） |
| 构建 | hatchling |

---

## 3. 分层总览

```text
┌─────────────────────────────────────────────────────────────┐
│ API Layer（api/v1/）  参数校验 → 调 Service → 返回 JSON       │
├─────────────────────────────────────────────────────────────┤
│ Middleware（middleware/）  限流（固定窗口计数器）              │
├─────────────────────────────────────────────────────────────┤
│ Service Layer（service/）  业务编排：聚合多 domain            │
├─────────────────────────────────────────────────────────────┤
│ Repository Layer（repository/）  缓存命中判断 → 调 Provider    │
├─────────────────────────────────────────────────────────────┤
│ Provider Layer（provider/）  AkShare 多源 fallback            │
├─────────────────────────────────────────────────────────────┤
│ Storage（DB）+ Cache（Redis）  慢变落库 / 快变缓存             │
└─────────────────────────────────────────────────────────────┘

旁路：
  Scheduler（scheduler/）  定时预热：股票/ETF/行业映射/搜索索引
  Search Index（search/）   内存索引（Trie 打分，毫秒级检索）
```

### 各层职责

| 层 | 目录 | 职责 | 不允许做的事 |
|----|------|------|------------|
| API | `api/v1/` | 参数校验、调 Service、返回 `ok(data)` | 不含业务逻辑、不直接调 Provider |
| Service | `service/` | 业务编排（过滤/排序/分页） | 不感知数据源、不写 SQL |
| Repository | `repository/` | 缓存命中判断、调 Provider | 不做业务聚合 |
| Provider | `provider/` | AkShare 调用（多源 fallback） | 不做缓存策略 |
| Storage | `storage/` | ORM 读写 | 不调外部数据源 |
| Cache | `cache/` | Redis/内存双实现 | 不做业务判断 |

---

## 4. 目录结构

```text
scx_stock/
├── api/                        # API 层
│   ├── v1/
│   │   ├── stock.py            # GET /stock/list、GET /stock/{code}
│   │   ├── search.py           # GET /search、GET /search/index-size
│   │   ├── sector.py           # GET /sector/list、GET /sector/{name}
│   │   └── market.py           # GET /market/index、GET /market/index/all
│   ├── deps.py                 # 依赖注入（Service / Cache）
│   ├── errors.py               # 全局异常 → 统一 JSON
│   └── router.py               # v1 路由聚合（前缀 /api/v1）
│
├── service/                    # 业务编排层
│   ├── stock_service.py        # 行情列表（过滤+排序+分页）、个股详情
│   ├── search_service.py       # 搜索
│   ├── sector_service.py       # 板块排行+详情
│   └── index_service.py        # 大盘指数
│
├── repository/                 # 缓存 + Provider 编排
│   ├── router.py               # StockRepository（行情/详情）
│   ├── sector_repo.py          # SectorRepository（板块）
│   └── index_repo.py           # IndexRepository（指数）
│
├── provider/                   # 数据源抽象
│   ├── contracts.py            # Protocol 接口（StockProvider 等）
│   ├── base.py                 # SyncProviderBase + UA 注入 + 代理绕过
│   └── akshare_provider.py     # AkShare 多源 fallback 实现
│
├── storage/                    # 持久化
│   ├── db.py                   # 异步引擎/会话/自动建库
│   ├── models.py               # ORM：stock / kline / market_calendar / stock_industry
│   └── repo.py                 # 批量 upsert / 全量加载
│
├── cache/
│   ├── backend.py              # CacheBackend 抽象 + RedisCache + MemoryCache
│   └── keys.py                 # 缓存键命名规则（PREFIX = "scx"）
│
├── search/                     # 搜索索引（内存）
│   ├── index.py（在 __init__.py）  # SearchIndex（打分/前缀/线程安全）
│   └── pinyin.py               # 拼音转换（pypinyin）
│
├── schema/                     # Pydantic 响应模型
│   ├── common.py               # ApiResponse / PageData / HealthStatus / ok() / fail()
│   ├── stock.py                # StockListItem / StockInfo / Quote / StockDetailResponse
│   ├── sector.py               # SectorQuote / SectorDetail
│   └── index.py                # IndexQuote（在 __init__.py）
│
├── exceptions/                 # 异常分层
│   ├── provider.py             # ProviderError / ProviderUnavailableError / ...
│   └── service.py              # ServiceError / NotFoundError / ValidationError / RateLimitExceededError
│
├── middleware/
│   └── rate_limit.py           # 限流（固定窗口，get_client_ip + check_rate_limit + ai_rate_limit）
│
├── scheduler/
│   ├── runner.py               # APScheduler 封装 + 调度计划
│   └── sync_jobs.py            # 4 个同步任务
│
├── config/
│   ├── settings.py             # 全局配置（环境变量前缀 SCX_）
│   └── datasource.py           # 数据源能力声明表
│
├── llm/                        # LLM/AI 分析（预留，未实现）
│
└── main.py                     # FastAPI 入口（lifespan + CORS + 异常 + 健康 + 运维 + 路由）
```

---

## 5. 多数据源 Fallback 机制（核心）

**背景**：AkShare 底层调用东方财富 `push2.eastmoney.com`，该域名在云服务器（阿里云 ECS）IP 段被反爬封锁（`RemoteDisconnected`）。通过多源 fallback 保证可用性。

### 5.1 `_call_with_fallback` 工作原理

`AkshareProvider._call_with_fallback(sources, domain)` 按优先级尝试多个数据源函数，第一个成功就返回 `(源名, DataFrame)`：

```python
sources = [
    ("em",   ak.stock_zh_a_spot_em, {}),    # 东方财富（字段全）
    ("sina", ak.stock_zh_a_spot,    {}),    # 新浪（字段少但云可用）
    ("tx",   ak.stock_zh_a_spot_tx, {}),    # 腾讯（含换手率+主力资金）
]
source, df = await self._call_with_fallback(sources, domain="list_stock_quotes")
```

### 5.2 各领域的 fallback 链

| 方法 | 主源 | 备选 1 | 备选 2 | 备注 |
|------|------|--------|--------|------|
| `list_stock_quotes` | 东方财富 `_em` | 新浪 `stock_zh_a_spot` | 腾讯 `stock_zh_a_spot_tx` | 腾讯含主力资金 `zljlr` |
| `get_quote` | 东方财富 `_em` | 新浪 | 腾讯 | 腾讯代码格式 `sh600519` |
| `list_stocks` | 东方财富 `_em` | 新浪 | 腾讯 | 搜索索引用 |
| `list_etfs` / `list_etf_quotes` | 东方财富 `fund_etf_spot_em` | 同花顺 `fund_etf_spot_ths` | — | |
| `list_sectors` | 东方财富 `stock_board_industry_name_em` | 新浪 `stock_sector_spot` | — | |
| `list_indexes` | 东方财富 `stock_zh_index_spot_em` | 新浪 `stock_zh_index_spot_sina` | — | |
| `get_stock` | 东方财富 `stock_individual_info_em` | — | — | 仅东方财富 |
| `get_sector_constituents` | 东方财富 `stock_board_industry_cons_em` | — | — | 仅东方财富（Scheduler 用） |

### 5.3 腾讯源列名映射

腾讯源列名是拼音缩写（与东方财富/新浪的中文列名完全不同），有独立映射函数：

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

### 5.4 Provider 层 monkey-patch（`provider/base.py`）

模块加载时对 `requests.Session.request` 打补丁：
1. **注入浏览器 User-Agent**：东方财富会拒绝无 UA 的请求
2. **国内数据源绕过代理**：`push2.eastmoney.com` 等域名设 `proxies={}` 直连，避免代理 SSL 干扰

---

## 6. 数据库 Schema

### 6.1 ORM 模型（`storage/models.py`）

| 表名 | 用途 | 主要字段 | 数据状态 |
|------|------|---------|---------|
| `stock` | 股票/ETF 基础信息 | code(PK), name, market, pinyin, type(PK), updated_at；唯一约束 (code, type) | ✅ Scheduler 每日同步 |
| `stock_industry` | 行业映射 | code(PK), industry, updated_at | ✅ Scheduler 每日同步 |
| `kline` | 历史 K 线 | id(PK), code, trade_date, ohlcv；唯一约束 (code, trade_date) | ⏳ 表已定义，无数据写入 |
| `market_calendar` | 交易日历 | trade_date(PK), is_open | ⏳ 表已定义，无数据写入 |

### 6.2 自动建库

`storage/db.py` 的 `init_db()` 在应用启动时（lifespan）执行：
- 连接维护库（postgres），检查目标库是否存在
- 不存在则创建（`SCX_DB_AUTO_CREATE=true` 时，开发期便利）
- `Base.metadata.create_all` 自动建表

### 6.3 持久化策略

| 数据 | 变化速度 | 存储 | TTL |
|------|---------|------|-----|
| 实时行情 | 秒级 | Redis | 30s（个股）/ 120s（列表） |
| 板块/指数 | 分钟级 | Redis | 120s |
| 搜索结果 | 分钟级 | Redis | 60s |
| 股票/ETF 列表 | 日级 | DB + Redis | 每日 09:00 同步 |
| 行业映射 | 日级 | DB | 每日 09:15 同步 |

---

## 7. 搜索设计

### 7.1 流程

```text
Scheduler 每日 09:20 → 从 DB 全量加载 → search/index.py 构建内存索引
                                        ↓
搜索请求 → SearchIndex.search(keyword) → 毫秒级返回
```

### 7.2 支持的匹配维度

- 精确代码：`510300`（score 100）
- 简称包含：`茅台`（score 80）
- 拼音全拼：`guizhou`（score 60/50）
- 拼音首字母：`gzmt`（score 40/30）

---

## 8. 限流设计

`middleware/rate_limit.py` 实现端点级限流：

- **算法**：固定窗口计数器（按分钟）
- **存储**：复用 `CacheBackend.incr`（Redis `INCR`+`EXPIRE` / Memory 字典）
- **标识**：客户端 IP（`X-Forwarded-For` → `X-Real-IP` → `request.client.host`）
- **命中**：抛 `RateLimitExceededError` → 429 + code 42901 + `Retry-After` 头
- **配置**：`SCX_AI_RATE_LIMIT_PER_MINUTE`（默认 20，为 AI 端点预留）

使用方式（未来 AI 端点）：
```python
@router.post("/analyze")
async def analyze(_=Depends(ai_rate_limit())):
    ...
```

---

## 9. 定时同步（Scheduler）

### 9.1 调度计划（`scheduler/runner.py`，时区 Asia/Shanghai）

| 任务 | Cron（周一至五） | 说明 |
|------|:---:|------|
| `sync_stock_list` | `0 9 * * 1-5` | 实际调 `sync_all`（串行：股票+ETF+行业+索引） |
| `sync_etf_list` | `10 9 * * 1-5` | ETF 列表 |
| `sync_stock_industries` | `15 9 * * 1-5` | 行业映射（板块成分股反查） |
| `rebuild_search_index` | `20 9 * * 1-5` | 重建内存搜索索引 |

### 9.2 容错

所有同步任务独立容错：单步失败返回 0 计数，不阻断后续步骤。

---

## 10. 统一响应与错误码

### 10.1 成功响应

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

### 10.2 错误码体系

| code | HTTP | 异常 | 含义 |
|------|------|------|------|
| 40001 | 400 | `ValidationError` | 业务校验失败 |
| 40401 | 404 | `NotFoundError` | 资源不存在 |
| 42201 | 422 | `RequestValidationError` | 请求参数校验失败（FastAPI 自动） |
| 42901 | 429 | `RateLimitExceededError` | 请求超限流（附 `Retry-After` 头） |
| 50001 | 500 | `ServiceError` | 服务异常 |
| 50201 | 502 | `ProviderError` | 数据源异常（上游不可用） |

---

## 11. 关键工程约束

1. **AkShare 同步库必须 `to_thread` 包装**：`SyncProviderBase._run` 推入线程池，避免阻塞事件循环
2. **实时行情必须缓存兜底**：数据源有限速，前端永远打缓存
3. **多源 fallback**：东方财富不可用时自动切换新浪/腾讯

---

## 12. 待实现

| 功能 | 状态 | 说明 |
|------|------|------|
| ETF 详情 `GET /etf/{code}` | ❌ | 当前 `/stock/{code}` 正则排除 ETF 代码 |
| 主力资金 `GET /fund_flow/{code}` | ❌ | 腾讯源已有 `zljlr` 字段可复用 |
| K 线同步 | ❌ | 表已定义，无 Scheduler 写入 |
| AI 分析 `POST /ai/analyze` | ❌ | `llm/` 空包，限流已就绪 |
| 数据源主备 failover | ❌ | `repository/fallback.py` 设计稿，未实现 |
