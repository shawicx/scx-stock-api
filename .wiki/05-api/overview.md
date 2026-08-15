# API 总览

> 路由聚合机制、认证挂载、统一响应、错误码、限流。共 29 个端点。

源码：`scx_stock/api/router.py`、`scx_stock/main.py`、`scx_stock/api/errors.py`、`scx_stock/middleware/`。

---

## 1. 路由聚合（`api/router.py`）

```python
# 公开路由（无认证）
public_router = APIRouter(prefix="/api/v1")
public_router.include_router(auth.router)       # /api/v1/auth/*

# 需认证路由
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_access_token)])
api_router.include_router(stock.router)         # /api/v1/stock/*
api_router.include_router(search.router)       # /api/v1/search/*
api_router.include_router(sector.router)       # /api/v1/sector/*
api_router.include_router(market.router)       # /api/v1/market/*
api_router.include_router(gold.router)         # /api/v1/market/gold
api_router.include_router(analysis.router)     # /api/v1/analysis/*
api_router.include_router(watchlist.router)    # /api/v1/watchlist/*
api_router.include_router(settings.router)     # /api/v1/settings/*
```

`main.py` 还直接定义了 `/health*`（无认证）和 `/admin/*`（需认证）端点。

---

## 2. 认证

除 `/health*` 和 `/api/v1/auth/*` 外，所有接口需认证。

请求头：`X-Access-Token: <token>` 或 `Authorization: Bearer <token>`。

两种 token：
1. **固定测试 token**：`.env` 设 `SCX_TEST_TOKEN`，匹配即通过（开发/测试）
2. **动态授权码**：16 位大写字母+数字，TTL 默认 3 天（`SCX_AUTH_CODE_TTL_HOURS` 可配），存 `auth_code` 表

详见 [认证机制](auth.md)。

---

## 3. 统一响应格式

所有接口（成功与错误）统一返回：

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | 业务码，**0 = 成功**，非 0 = 业务错误 |
| `message` | string | 描述信息，成功为 `"ok"` |
| `data` | any | 业务数据，错误时为 `null` |

### 错误码

| code | HTTP | 含义 |
|------|------|------|
| 40001 | 400 | 业务校验失败（`ValidationError`） |
| 40401 | 404 | 资源不存在（`NotFoundError`） |
| 42201 | 422 | 请求参数校验失败（FastAPI 自动） |
| 42901 | 429 | 请求超限流（附 `Retry-After` 头，秒） |
| 50001 | 500 | 服务异常（`ServiceError`） |
| 50201 | 502 | 数据源异常（`ProviderError`） |

异常处理在 `scx_stock/api/errors.py:register_exception_handlers`。

---

## 4. 限流

`middleware/rate_limit.py` 实现端点级限流（固定窗口计数器）：

- **算法**：按分钟固定窗口，复用 `CacheBackend.incr`（Redis `INCR`+`EXPIRE` / Memory 字典）
- **标识**：客户端 IP（`X-Forwarded-For` → `X-Real-IP` → `request.client.host`）
- **配置**：`SCX_AI_RATE_LIMIT_PER_MINUTE`（默认 20）
- **应用**：通过 `Depends(ai_rate_limit())` 挂在 `POST /analysis/run`、`POST /settings/test-llm`、`POST /settings/test-smtp`
- **命中**：抛 `RateLimitExceededError` → 429 + `code 42901` + `Retry-After` 头

> 无全局限流中间件，仅上述 3 个端点限流。

---

## 5. 端点索引（29 个）

| 类别 | 端点 | 文档 |
|------|------|------|
| 认证 | `POST /api/v1/auth/request-code` `/verify` `/logout` | [auth.md](auth.md) |
| 行情 | `GET /api/v1/stock/list`、`GET /api/v1/stock/{code}` | [quotes.md](quotes.md) |
| 搜索 | `GET /api/v1/search`、`GET /api/v1/search/index-size` | [quotes.md](quotes.md) |
| 板块 | `GET /api/v1/sector/list`、`GET /api/v1/sector/{name}` | [sectors-indexes-gold.md](sectors-indexes-gold.md) |
| 指数 | `GET /api/v1/market/index`、`GET /api/v1/market/index/all` | [sectors-indexes-gold.md](sectors-indexes-gold.md) |
| 黄金 | `GET /api/v1/market/gold` | [sectors-indexes-gold.md](sectors-indexes-gold.md) |
| 分析 | `POST /api/v1/analysis/run`、`GET .../latest` `/history` `/report/{date}` | [analysis.md](analysis.md) |
| 关注列表 | `GET/POST/PUT/DELETE /api/v1/watchlist` | [watchlist.md](watchlist.md) |
| 配置 | `GET/PUT /api/v1/settings`、`POST .../test-llm` `/test-smtp` | [settings.md](settings.md) |
| 健康 | `GET /health`、`GET /health/ready` | [health-admin.md](health-admin.md) |
| 运维 | `POST /admin/sync`、`POST /admin/reindex`、`GET /admin/task/{id}` | [health-admin.md](health-admin.md) |

交互式文档：启动后访问 `http://localhost:8000/docs`（Swagger UI）或 `/redoc`。

---

## Related

- [前端联调指南](../09-frontend-integration/frontend-guide.md)
- [架构分层](../01-overview/architecture.md)
- [代码结构](../03-codebase/codebase.md)
