# 开发指南

> 测试、调试、编码规范、依赖管理、常见问题。

---

## 1. 测试

### 1.1 运行

```bash
uv run pytest                         # 全部
uv run pytest tests/test_xxx.py       # 指定文件
uv run pytest -k "not test_unknown_stock"  # 跳过网络依赖测试
```

### 1.2 测试策略

所有测试用 mock 隔离外网和 DB，**不依赖真实 PostgreSQL / Redis / 东方财富**：

| 层 | mock 方式 |
|----|----------|
| Provider | `unittest.mock.patch` mock akshare 函数 |
| Repository | `MagicMock` + `AsyncMock` mock provider |
| Service | mock repository |
| API | `fastapi.testclient.TestClient` |

**唯一例外**：`test_smoke.py::test_unknown_stock_returns_graceful_error` 会真实调用 akshare（断言宽松：`status != 500`）。

### 1.3 pytest 配置（`pyproject.toml`）

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"    # async 测试无需 @pytest.mark.asyncio
pythonpath = ["."]       # flat-layout 导入
testpaths = ["tests"]
```

---

## 2. 调试技巧

### 2.1 开启 SQL 日志

```bash
SCX_DB_ECHO=true uv run uvicorn scx_stock.main:app --reload
```

### 2.2 开启 DEBUG 日志

```bash
SCX_LOG_LEVEL=DEBUG uv run uvicorn scx_stock.main:app --reload
```

### 2.3 测试单个 Provider 方法

```python
import asyncio
from scx_stock.provider.akshare_provider import AkshareProvider

async def main():
    p = AkshareProvider()
    items = await p.list_stock_quotes()
    print(f"{len(items)} items, first: {items[0]}")

asyncio.run(main())
```

### 2.4 清除缓存重新拉取

```bash
redis-cli FLUSHDB    # 清空当前 DB（开发期）
```

或重启应用（内存缓存自动清空）。

---

## 3. 编码规范（[`AGENTS.md`](../../AGENTS.md)）

### 3.1 注释要求（强制）

- 每个文件必须有 `@description` 文件头注释（中文）
- 每个函数必须有 `@description` / `@param` / `@returns`（JSDoc 风格）
- 核心函数需 `@example`

示例：

```python
"""
@description 从 Apifox 平台获取 OpenAPI 数据
"""

def fetch_data(config):
    """
    @description 获取 API 数据
    @param config API 配置对象
    @returns Promise<ApiData> API 数据
    """
```

### 3.2 依赖管理

- 包管理器固定 **uv**，禁止切换到 poetry/pip
- 禁止降级依赖版本
- 新增依赖用 `uv add <package>`（自动更新 `pyproject.toml` + `uv.lock`）
- 新增依赖遵循最新兼容版本策略（semver `^`）

### 3.3 禁止事项

- 不自动执行 `git commit` / `git push`（由用户审查后手动提交）
- 不擅自重构一级目录结构（`src`、`public`、`dist` 等）
- 不改 lint/build 行为（项目无 ruff/eslint 配置）
- 不改基础配置文件（`pyproject.toml` 的构建部分）
- 不把 `.venv` / `__pycache__` 提交入库

---

## 4. 常见问题

### Q: 启动后行情接口返回 50201 / `stock not found`

A: 数据源（AkShare）连不上。常见原因：
- 本地有代理（Clash/Surge）干扰东方财富 HTTPS，检查 `SCX_*` 代理环境变量
- 部署到云服务器时东方财富 IP 被封，依赖多源 fallback（新浪/腾讯）

### Q: 搜索返回空数组

A: 内存索引未构建。执行 `POST /admin/sync` 触发同步。

### Q: DB 连接失败但应用仍能启动

A: 设计如此。`init_db()` 容错，DB 不可用只记 warning 不阻断启动（便于无 DB 调试 Provider）。

### Q: 接口返回 401 `缺少授权码`

A: 未带 `X-Access-Token` 头，或 token 无效/过期。开发环境可设 `SCX_TEST_TOKEN` 用固定 token。

### Q: 如何添加新的数据源

A: 在 `AkshareProvider._call_with_fallback` 的 sources 列表中追加。无需新建 Provider 类——所有 akshare 函数都在同一个 Provider 内 fallback。详见 [04-data-providers/fallback](../04-data-providers/fallback.md)。

### Q: LLM 解读不生效

A: 检查 `llm_api_key` 是否配置（前端 `/settings` 或 `.env`）。未配置时自动降级为规则模板摘要，不报错。

### Q: 每日分析邮件没发

A: 检查：
1. 当天是否交易日（非交易日 `daily_analysis_job` 跳过）
2. `notify_emails` 是否配置（动态配置 DB > `.env`）
3. `success > 0`（全失败不发）
4. SMTP 配置是否正确（可用 `POST /settings/test-smtp` 测试）

---

## Related

- [快速上手](../02-getting-started/quick-start.md)
- [代码结构](../03-codebase/codebase.md)
- [环境变量](../08-configuration/environment-variables.md)
- [AGENTS.md](../../AGENTS.md)
