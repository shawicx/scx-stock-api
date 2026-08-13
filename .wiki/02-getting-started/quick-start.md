# 快速上手

> 从零启动 scx-stock-api 并验证核心功能。

---

## 1. 环境准备

### 1.1 必装

- **Python ≥3.13**（`pyproject.toml` 要求 `requires-python = ">=3.13"`）
- **uv**（包管理器，[安装指南](https://docs.astral.sh/uv/)）
- **PostgreSQL**（开发期可选，应用会自动建库）
- **Redis**（可选，无 Redis 时回退内存缓存）

### 1.2 快速启动

```bash
# 1. 克隆
git clone https://github.com/shawicx/scx-stock-api.git
cd scx-stock-api

# 2. 安装依赖（uv 会自动创建 .venv）
uv sync --group dev

# 3. 配置
cp .env.example .env
# 按需修改 .env（DB/Redis/LLM/SMTP 连接）

# 4. 启动（开发模式，热重载）
uv run uvicorn scx_stock.main:app --reload --port 8000

# 5. 验证
curl http://localhost:8000/health
curl http://localhost:8000/docs    # Swagger UI
```

### 1.3 首次数据同步

应用启动后内存搜索索引为空（lifespan 不重建索引，需等调度任务或手动触发），需手动触发一次全量同步：

```bash
curl -X POST http://localhost:8000/admin/sync \
  -H "X-Access-Token: <你的授权码或测试token>"
```

这会异步串行执行：股票列表 → ETF 列表 → 行业映射 → 重建搜索索引。通过返回的 `task_id` 轮询进度：

```bash
curl http://localhost:8000/admin/task/<task_id> \
  -H "X-Access-Token: <token>"
```

---

## 2. 认证

除 `/health*` 和 `/api/v1/auth/*` 外，所有接口需认证。两种方式：

1. **固定测试 token**（开发/测试用）：`.env` 设置 `SCX_TEST_TOKEN=xxx`，请求头 `X-Access-Token: xxx`
2. **动态授权码**：`POST /api/v1/auth/request-code` → 邮件收到 16 位码 → 请求头 `X-Access-Token: <码>`

详见 [认证机制](../05-api/auth.md)。

---

## 3. 配置要点

所有配置通过 `SCX_` 前缀环境变量或 `.env` 注入。最常改动的：

| 环境变量 | 说明 |
|---------|------|
| `SCX_DB_HOST` / `SCX_DB_PORT` | PostgreSQL（开发默认 5433） |
| `SCX_REDIS_HOST` / `SCX_REDIS_PORT` | Redis（开发默认 6379） |
| `SCX_CORS_ORIGINS` | 前端源（逗号分隔，`*` = 全部） |
| `SCX_LLM_*` | LLM 配置（provider/key/base_url/model） |
| `SCX_SMTP_*` | 邮件配置（QQ 邮箱需用授权码） |
| `SCX_WATCHLIST` | 每日分析的关注代码（逗号分隔） |
| `SCX_NOTIFY_EMAILS` | 每日报告收件人（逗号分隔） |

完整配置见 [08-configuration/environment-variables](../08-configuration/environment-variables.md)。

> **重要**：`.env` 文件不支持行内注释（`# 注释` 会破坏 pydantic 解析）。注释单独成行。

---

## 4. 常见启动问题

| 现象 | 原因 / 解决 |
|------|------------|
| 行情接口 50201 / `stock not found` | AkShare 连不上。检查代理（Clash/Surge）干扰东方财富 HTTPS，或云服务器 IP 被封（依赖多源 fallback） |
| 搜索返回空数组 | 内存索引未构建。执行 `POST /admin/sync` |
| 接口 401 `缺少授权码` | 未带 `X-Access-Token` 头，或 token 无效 |
| DB 连接失败但应用仍启动 | 设计如此。`init_db()` 容错，便于无 DB 调试 |

---

## Related

- [项目概述](../01-overview/project-overview.md)
- [配置项全量](../08-configuration/environment-variables.md)
- [认证机制](../05-api/auth.md)
- [开发指南](../11-development/development.md)
