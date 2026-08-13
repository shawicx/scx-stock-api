# 架构

> 分层架构、各层职责、目录结构、统一响应、工程约束。

---

## 1. 分层总览

```text
┌─────────────────────────────────────────────────────────────┐
│ API Layer（api/v1/）  参数校验 → 调 Service → 返回 JSON       │
├─────────────────────────────────────────────────────────────┤
│ Middleware（middleware/）  认证 + 限流（固定窗口计数器）        │
├─────────────────────────────────────────────────────────────┤
│ Service Layer（service/）  业务编排：过滤/排序/分页            │
├─────────────────────────────────────────────────────────────┤
│ Repository Layer（repository/）  缓存命中判断 → 调 Provider    │
├─────────────────────────────────────────────────────────────┤
│ Provider Layer（provider/）  AkShare 多源 fallback            │
├─────────────────────────────────────────────────────────────┤
│ Storage（DB）+ Cache（Redis）  慢变落库 / 快变缓存             │
└─────────────────────────────────────────────────────────────┘

旁路：
  Scheduler（scheduler/）     定时同步 + 每日分析
  Analysis（analysis/）        支撑位分析引擎
  LLM（llm/）                  AI 解读（失败降级模板）
  Notify（notify/）            邮件发送
  Search Index（search/）      内存索引（Trie 打分）
```

## 2. 各层职责

| 层 | 目录 | 职责 | 不允许做的事 |
|----|------|------|------------|
| API | `api/v1/` | 参数校验、调 Service、返回 `ok(data)` | 不含业务逻辑、不直接调 Provider |
| Service | `service/` | 业务编排（过滤/排序/分页） | 不感知数据源、不写 SQL |
| Repository | `repository/` | 缓存命中判断、调 Provider | 不做业务聚合 |
| Provider | `provider/` | AkShare 调用（多源 fallback） | 不做缓存策略 |
| Storage | `storage/` | ORM 读写（`storage/repo.py`） | 不调外部数据源 |
| Cache | `cache/` | Redis/内存双实现 | 不做业务判断 |

> 完整目录树见 [03-codebase](../03-codebase/codebase.md)。

## 3. 多源 Fallback（核心）

AkShare 底层调用东方财富 `push2.eastmoney.com`，该域名在阿里云 ECS IP 段被反爬封锁。通过 `_call_with_fallback` 按优先级尝试多源，第一个成功即返回。

**重要**：fallback 顺序因方法而异，不要一概而论：
- **ETF 列表/报价**（`list_etfs` / `list_etf_quotes`）：新浪 → 东方财富 → 同花顺（新浪为第一源）
- **股票行情/列表/详情**（`list_stock_quotes` / `get_quote` / `list_stocks`）：东方财富 → 新浪 → 腾讯
- **板块/指数**：东方财富 → 新浪

详见 [04-data-providers/fallback](../04-data-providers/fallback.md)。

## 4. 统一响应与错误码

### 成功响应

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

### 错误码

| code | HTTP | 异常 | 含义 |
|------|------|------|------|
| 40001 | 400 | `ValidationError` | 业务校验失败 |
| 40401 | 404 | `NotFoundError` | 资源不存在 |
| 42201 | 422 | `RequestValidationError` | 请求参数校验失败（FastAPI 自动） |
| 42901 | 429 | `RateLimitExceededError` | 请求超限流（附 `Retry-After` 头） |
| 50001 | 500 | `ServiceError` | 服务异常 |
| 50201 | 502 | `ProviderError` | 数据源异常（上游不可用） |

异常处理在 `scx_stock/api/errors.py` 的 `register_exception_handlers`。

## 5. 关键工程约束

1. **AkShare 同步库必须 `to_thread` 包装**：`SyncProviderBase._run`（`provider/base.py:107`）推入线程池，避免阻塞事件循环
2. **实时行情必须缓存兜底**：数据源有限速，前端永远打缓存
3. **多源 fallback + validate 校验**：`_call_with_fallback` 支持 `validate` 回调，防御空 DataFrame / 列名不匹配静默失败
4. **东方财富超时优化**：`provider/base.py` 对东方财富域名强制 `timeout=5s`（AkShare 默认 15s × 3 次重试太慢）
5. **K 线 DB 优先读**：分析时优先从 DB 读 K 线，DB 不足时 fallback Provider 拉取并回填 DB
6. **动态配置**：LLM/SMTP 配置优先读 DB `app_setting` 表（前端修改即时生效），`.env` 作为回退默认值
7. **认证**：`middleware/auth.py` 校验 `X-Access-Token` 头，支持固定测试 token + 动态授权码两种方式
8. **DB 不可用不阻断启动**：`init_db()` 容错，失败只 warning（便于无 DB 调试 Provider）

---

## Related

- [项目概述](project-overview.md)
- [目录结构](../03-codebase/codebase.md)
- [多源 Fallback 详解](../04-data-providers/fallback.md)
- [API 总览](../05-api/overview.md)
