# 环境变量

> 全部 `SCX_` 前缀配置项（`config/settings.py`），类型、默认、说明。

源码：`scx_stock/config/settings.py`。`Settings(BaseSettings)` + `env_prefix="SCX_"`，`.env` 解析于项目根。`get_settings()` 用 `@lru_cache` 单例。

> **重要**：`.env` 不支持行内注释（`# 独立PG` 会破坏 pydantic 解析）。注释单独成行或删除。

---

## 1. 应用

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_APP_NAME` | str | `scx-stock-api` | 应用名 |
| `SCX_APP_ENV` | Literal["dev","prod"] | `dev` | dev 时 uvicorn 启用 reload |
| `SCX_APP_HOST` | str | `0.0.0.0` | 监听地址 |
| `SCX_APP_PORT` | int | `8000` | 开发端口（生产 3800） |
| `SCX_LOG_LEVEL` | str | `INFO` | 日志级别 |

---

## 2. 数据库（PostgreSQL）

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_DB_HOST` | str | `127.0.0.1` | |
| `SCX_DB_PORT` | int | `5433` | 开发 5433；生产独立容器 5434 |
| `SCX_DB_USER` | str | `scx` | |
| `SCX_DB_PASSWORD` | str | `your_secure_password_here` | |
| `SCX_DB_NAME` | str | `scx-stock` | |
| `SCX_DB_ECHO` | bool | `false` | SQL 日志 |
| `SCX_DB_AUTO_CREATE` | bool | `true` | 启动时自动建库（开发期） |

---

## 3. 缓存（Redis）

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_REDIS_HOST` | str | `127.0.0.1` | |
| `SCX_REDIS_PORT` | int | `6379` | 开发 6379；生产独立容器 6389 |
| `SCX_REDIS_DB` | int | `0` | |
| `SCX_REDIS_PASSWORD` | str\|null | `None` | 可选 |

---

## 4. 数据源与 Web

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_DEFAULT_PROVIDER` | str | `akshare` | 默认数据源 |
| `SCX_REQUEST_TIMEOUT` | int | `10` | 请求超时秒 |
| `SCX_CORS_ORIGINS` | str | 多个 localhost | 逗号分隔；`*` = 全部（关闭 credentials） |
| `SCX_DEFAULT_PAGE_SIZE` | int | `20` | 默认分页 |
| `SCX_MAX_PAGE_SIZE` | int | `100` | 最大分页 |
| `SCX_AI_RATE_LIMIT_PER_MINUTE` | int | `20` | AI 端点限流/分钟 |

---

## 5. 认证

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_TEST_TOKEN` | str | `""` | 固定测试 token（开发/测试，生产留空走授权码） |

---

## 6. 关注列表与分析任务

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_WATCHLIST` | str | `""` | 关注代码（逗号分隔，股票/ETF 均可），每日分析用 |
| `SCX_NOTIFY_EMAILS` | str | `""` | 每日报告收件人（逗号分隔） |
| `SCX_ANALYSIS_CRON` | str | `0 21 * * 1-5` | 每日分析 cron（Asia/Shanghai） |
| `SCX_ANALYSIS_KLINE_DAYS` | int | `120` | K 线窗口（交易日数） |

---

## 7. LLM 配置（OpenAI 兼容）

> 这些键支持[动态配置](dynamic-config.md)（前端 `/settings` 修改即时生效）。

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_LLM_PROVIDER` | Literal["glm","deepseek"] | `deepseek` | 厂商 |
| `SCX_LLM_API_KEY` | str | `""` | API Key |
| `SCX_LLM_BASE_URL` | str | `https://api.deepseek.com/v1` | 接口地址 |
| `SCX_LLM_MODEL` | str | `deepseek-chat` | 模型名 |
| `SCX_LLM_TIMEOUT` | int | `30` | 超时秒 |

参考值：
- DeepSeek：`base_url=https://api.deepseek.com/v1`, `model=deepseek-chat`
- GLM：`base_url=https://open.bigmodel.cn/api/paas/v4`, `model=glm-4-flash`

---

## 8. SMTP 邮件配置

> 这些键支持[动态配置](dynamic-config.md)。QQ 邮箱 `password` 为授权码。

| 环境变量 | 类型 | 默认 | 说明 |
|---------|------|------|------|
| `SCX_SMTP_HOST` | str | `""` | SMTP 主机 |
| `SCX_SMTP_PORT` | int | `465` | 端口（465→TLS，587→STARTTLS） |
| `SCX_SMTP_USER` | str | `""` | 账号 |
| `SCX_SMTP_PASSWORD` | str | `""` | 密码/授权码 |
| `SCX_SMTP_FROM_NAME` | str | `ETF日报` | 发件人名 |
| `SCX_SMTP_USE_SSL` | bool | `true` | 标记位（实际加密由端口决定） |

---

## 9. 辅助方法（`settings.py`）

| 方法 | 说明 |
|------|------|
| `cors_origin_list()`（`:115`） | `SCX_CORS_ORIGINS` 拆分列表 |
| `watchlist_codes()`（`:122`） | `SCX_WATCHLIST` 拆分代码列表 |
| `notify_email_list()`（`:129`） | `SCX_NOTIFY_EMAILS` 拆分邮箱列表 |
| `get_dsn()`（`:146`） | 构建 `postgresql+asyncpg://...` |

---

## Related

- [动态配置机制](dynamic-config.md)
- [应用配置接口](../05-api/settings.md)
- [快速上手](../02-getting-started/quick-start.md)
- [部署指南](../10-deployment/deployment.md)
