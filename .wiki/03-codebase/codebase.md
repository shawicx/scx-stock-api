# 代码结构

> 完整目录树、各包职责、入口 `main.py` lifespan 流程、依赖方向。

---

## 1. 目录结构

```text
scx_stock/
├── main.py                     # FastAPI 入口（lifespan + CORS + 异常 + 健康 + 运维 + 认证 + 路由）
│
├── api/                        # API 层
│   ├── v1/
│   │   ├── stock.py            # GET /stock/list、GET /stock/{code}
│   │   ├── search.py           # GET /search、GET /search/index-size
│   │   ├── sector.py           # GET /sector/list、GET /sector/{name}
│   │   ├── market.py           # GET /market/index、GET /market/index/all
│   │   ├── gold.py             # GET /market/gold
│   │   ├── analysis.py         # POST /analysis/run、GET /analysis/latest|history|report
│   │   ├── watchlist.py        # GET/POST/PUT/DELETE /watchlist
│   │   ├── settings.py         # GET/PUT /settings、POST /settings/test-llm|test-smtp
│   │   └── auth.py             # POST /auth/request-code|verify|logout（公开，无认证）
│   ├── deps.py                 # 依赖注入（Service / Cache）
│   ├── errors.py               # 全局异常 → 统一 JSON
│   └── router.py               # v1 路由聚合（public_router 无认证 + api_router 带认证）
│
├── service/                    # 业务编排层
│   ├── stock_service.py        # 行情列表（过滤+排序+分页）、个股详情
│   ├── search_service.py       # 搜索
│   ├── sector_service.py       # 板块排行+详情
│   ├── index_service.py        # 大盘指数（白名单过滤）
│   └── gold_service.py         # 黄金行情
│
├── repository/                 # 缓存 + Provider 编排
│   ├── router.py               # StockRepository（行情/详情，TTL 30/300/120s）
│   ├── sector_repo.py          # SectorRepository（板块，TTL 120s）
│   ├── index_repo.py           # IndexRepository（指数 + 白名单，TTL 120s）
│   └── gold_repo.py            # GoldRepository（黄金，TTL 120s）
│
├── provider/                   # 数据源抽象
│   ├── contracts.py            # Protocol 接口（StockProvider / KlineProvider / IndexProvider）
│   ├── base.py                 # SyncProviderBase + UA 注入 + 代理绕过 + 东方财富超时优化
│   └── akshare_provider.py     # AkShare 多源 fallback 实现（含 validate 校验）
│
├── storage/                    # 持久化
│   ├── db.py                   # 异步引擎/会话/自动建库
│   ├── models.py               # ORM：8 张表
│   └── repo.py                 # 批量 upsert / 全量加载 / K线读写 / 交易日历 / 授权码 / 配置 / 关注列表
│
├── cache/
│   ├── backend.py              # CacheBackend 抽象 + RedisCache + MemoryCache
│   └── keys.py                 # 缓存键命名规则（PREFIX = "scx"）
│
├── search/                     # 搜索索引（内存）
│   ├── index.py                # SearchIndex（打分/前缀/线程安全 RLock）
│   └── pinyin.py               # 拼音转换（pypinyin）
│
├── schema/                     # Pydantic 响应模型
│   ├── common.py               # ApiResponse / PageData / HealthStatus / ok() / fail()
│   ├── stock.py                # StockListItem / StockInfo / Quote / StockDetailResponse
│   ├── sector.py               # SectorQuote / SectorDetail
│   ├── index.py                # IndexQuote
│   ├── gold.py                 # GoldQuote
│   ├── kline.py                # Kline / KlineBar
│   └── analysis.py             # SupportLevel / AnalysisReport
│
├── exceptions/                 # 异常分层
│   ├── provider.py             # ProviderError / ProviderUnavailableError
│   └── service.py              # ServiceError / NotFoundError / ValidationError / RateLimitExceededError
│
├── middleware/
│   ├── rate_limit.py           # 限流（固定窗口，get_client_ip + check_rate_limit + ai_rate_limit）
│   └── auth.py                 # 授权码校验依赖（X-Access-Token / 固定 token）
│
├── analysis/                   # 支撑位分析引擎
│   ├── indicators.py           # 技术指标（MA/BOLL/Pivot/前低前高）
│   ├── support.py              # 支撑/压力位候选收集+聚类(1%容差)+打分(强弱)
│   ├── trend.py                # 趋势判断（均线排列：多头/空头/震荡）
│   └── engine.py               # 编排：K线→指标→支撑位→趋势→结构化结果
│
├── llm/                        # AI 解读层
│   ├── client.py               # OpenAI 兼容客户端（GLM/DeepSeek，动态配置）
│   └── interpreter.py          # 结构化结果→LLM解读→摘要（失败降级模板）
│
├── notify/                     # 通知层
│   ├── email_sender.py         # aiosmtplib 异步发送（动态 SMTP 配置）
│   └── templates/
│       └── daily_report.html   # jinja2 邮件模板
│
├── scheduler/
│   ├── runner.py               # APScheduler 封装 + 调度计划（7 个任务，Asia/Shanghai）
│   ├── sync_jobs.py            # 同步任务（股票/ETF/行业/索引/K线/交易日历）
│   ├── analysis_job.py         # 每日支撑位分析任务（DB优先读K线+落库+发邮件）
│   └── task_manager.py         # 后台异步任务管理（全量同步进度轮询）
│
└── config/
    ├── settings.py             # 全局配置（环境变量前缀 SCX_，@lru_cache 单例）
    ├── dynamic.py              # 动态配置读取（DB app_setting 优先，.env 回退）
    └── datasource.py           # 数据源能力声明表（CAPABILITIES + select_providers）
```

---

## 2. 入口 main.py

`scx_stock/main.py` 版本 `__version__ = "0.1.0"`。

### 2.1 lifespan 启动流程

```text
lifespan(app):
  1. get_settings() → 日志 "starting {app_name} (env={app_env})"
  2. await init_db()              # 建表；失败只 warning，不阻断启动
  3. get_scheduler() → setup() → scheduler.start()   # 启动 APScheduler
  4. yield                        # 应用运行期
  5. shutdown: scheduler.shutdown() → await close_db()
```

> **注意**：lifespan 不重建搜索索引。索引由调度任务（周一至周五 09:20）或 `POST /admin/reindex` 构建。首次启动后索引为空。

### 2.2 create_app 注册顺序

```text
create_app():
  1. _register_cors(app)              # CORSMiddleware（"*" 时关闭 credentials）
  2. register_exception_handlers(app) # 6 类异常 → 统一 JSON
  3. _register_health(app)            # /health、/health/ready（无认证）
  4. _register_admin(app)             # /admin/sync|reindex|task（需认证）
  5. public_router 挂载               # /api/v1/auth/*（无认证）
  6. api_router 挂载                  # /api/v1/*（需认证）
```

### 2.3 `python -m scx_stock`

`main.py` 的 `__main__` 以 `reload = (app_env == "dev")` 启动 uvicorn。

---

## 3. 依赖方向

```text
main.py
  ↓
api/v1/*  →  service/*  →  repository/*  →  provider/*  →  AkShare（外部）
                ↓              ↓
            schema/*      cache/*（Redis）
                            ↓
                       storage/*（PostgreSQL）

旁路（不经过 API 层）：
  scheduler/*  →  sync_jobs → provider + storage
              →  analysis_job → analysis/* + llm/* + notify/* + storage
  search/*     ←  scheduler.rebuild_search_index + api/v1/search
```

**禁止反向依赖**：Provider 不依赖 Repository，Repository 不依赖 Service，Service 不依赖 API。

---

## 4. 测试目录

```text
tests/
├── conftest.py             # pytest 夹具
├── test_smoke.py           # 冒烟（含 1 个真实 akshare 调用）
└── test_*.py               # 其余全 mock 隔离
```

测试策略详见 [11-development](../11-development/development.md)。

---

## Related

- [架构分层](../01-overview/architecture.md)
- [多源 Fallback](../04-data-providers/fallback.md)
- [数据模型](../06-data/data-model.md)
- [API 总览](../05-api/overview.md)
