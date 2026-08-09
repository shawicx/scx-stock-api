# 开发指南

> 面向新加入的开发者和 AI Agent，帮助快速上手。

---

## 1. 环境准备

### 1.1 必装

- **Python ≥3.13**（`requires-python = ">=3.13"`）
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
# 按需修改 .env（DB/Redis 连接）

# 4. 启动（开发模式，热重载）
uv run uvicorn scx_stock.main:app --reload --port 8000

# 5. 验证
curl http://localhost:8000/health
curl http://localhost:8000/docs    # Swagger UI
```

### 1.3 首次数据同步

应用启动后内存搜索索引为空，需手动触发一次全量同步：

```bash
curl -X POST http://localhost:8000/admin/sync
```

这会串行执行：股票列表 → ETF 列表 → 行业映射 → 重建搜索索引。

---

## 2. 配置项（`config/settings.py`）

所有配置通过环境变量（前缀 `SCX_`）或项目根 `.env` 文件注入。`get_settings()` 用 `@lru_cache` 单例。

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `SCX_APP_ENV` | `dev` | dev 时 uvicorn 启用 reload |
| `SCX_APP_HOST` | `0.0.0.0` | |
| `SCX_APP_PORT` | `8000` | 开发端口 |
| `SCX_LOG_LEVEL` | `INFO` | |
| `SCX_DB_HOST` | `127.0.0.1` | PostgreSQL |
| `SCX_DB_PORT` | `5433` | 开发用 5433；生产独立容器 5434 |
| `SCX_DB_USER` | `postgres` | |
| `SCX_DB_PASSWORD` | `postgres` | |
| `SCX_DB_NAME` | `scx-stock` | |
| `SCX_DB_ECHO` | `false` | SQL 日志 |
| `SCX_DB_AUTO_CREATE` | `true` | 启动时自动建库（开发期） |
| `SCX_REDIS_HOST` | `127.0.0.1` | |
| `SCX_REDIS_PORT` | `6379` | 开发 6379；生产独立容器 6389 |
| `SCX_REDIS_DB` | `0` | |
| `SCX_REDIS_PASSWORD` | — | 可选 |
| `SCX_DEFAULT_PROVIDER` | `akshare` | |
| `SCX_REQUEST_TIMEOUT` | `10` | 秒 |
| `SCX_CORS_ORIGINS` | 多个 localhost | 逗号分隔；`*` = 全部（关闭 credentials） |
| `SCX_DEFAULT_PAGE_SIZE` | `20` | |
| `SCX_MAX_PAGE_SIZE` | `100` | |
| `SCX_AI_RATE_LIMIT_PER_MINUTE` | `20` | AI 端点限流（预留） |

---

## 3. 测试

### 3.1 运行

```bash
uv run pytest                    # 全部
uv run pytest tests/test_xxx.py  # 指定文件
uv run pytest -k "not test_unknown_stock"  # 跳过网络依赖测试
```

### 3.2 测试策略

所有测试用 mock 隔离外网和 DB，**不依赖真实 PostgreSQL / Redis / 东方财富**：

- Provider 测试：`unittest.mock.patch` mock akshare 函数
- Repository 测试：`MagicMock` + `AsyncMock` mock provider
- Service 测试：mock repository
- API 测试：`fastapi.testclient.TestClient`

唯一例外：`test_smoke.py::test_unknown_stock_returns_graceful_error` 会真实调用 akshare（断言宽松：`status != 500`）。

### 3.3 pytest 配置

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"    # async 测试无需 @pytest.mark.asyncio
pythonpath = ["."]       # flat-layout 导入
testpaths = ["tests"]
```

---

## 4. 代码规范

### 4.1 注释要求（AGENTS.md 强制）

- 每个文件必须有 `@description` 文件头注释（中文）
- 每个函数必须有 `@description` / `@param` / `@returns`（JSDoc 风格）
- 核心函数需 `@example`

### 4.2 依赖管理

- 包管理器固定 **uv**，禁止切换到 poetry/pip
- 禁止降级依赖版本
- 新增依赖用 `uv add <package>`（自动更新 `pyproject.toml` + `uv.lock`）

### 4.3 禁止事项

- 不自动执行 `git commit` / `git push`
- 不擅自重构一级目录结构
- 不改 lint/build 行为（项目无 ruff/eslint 配置）
- 不改基础配置文件（pyproject.toml 的构建部分）

---

## 5. 调试技巧

### 5.1 开启 SQL 日志

```bash
SCX_DB_ECHO=true uv run uvicorn scx_stock.main:app --reload
```

### 5.2 开启 DEBUG 日志

```bash
SCX_LOG_LEVEL=DEBUG uv run uvicorn scx_stock.main:app --reload
```

### 5.3 测试单个 Provider 方法

```python
import asyncio
from scx_stock.provider.akshare_provider import AkshareProvider

async def main():
    p = AkshareProvider()
    items = await p.list_stock_quotes()
    print(f"{len(items)} items, first: {items[0]}")

asyncio.run(main())
```

### 5.4 清除缓存重新拉取

Redis CLI：
```bash
redis-cli FLUSHDB    # 清空当前 DB（开发期）
```

或重启应用（内存缓存自动清空）。

---

## 6. 常见问题

### Q: 启动后行情接口返回 404 / `stock not found: list`

A: 数据源（AkShare）连不上。常见原因：
- 本地有代理（Clash/Surge）干扰东方财富 HTTPS，检查 `SCX_*` 代理环境变量
- 部署到云服务器时东方财富 IP 被封，需依赖多源 fallback（新浪/腾讯）

### Q: 搜索返回空数组

A: 内存索引未构建。执行 `POST /admin/sync` 触发同步。

### Q: DB 连接失败但应用仍能启动

A: 设计如此。`init_db()` 容错，DB 不可用只记 warning 不阻断启动（便于无 DB 调试 Provider）。

### Q: 如何添加新的数据源

A: 在 `AkshareProvider._call_with_fallback` 的 sources 列表中追加。无需新建 Provider 类——所有 akshare 函数都在同一个 Provider 内 fallback。
