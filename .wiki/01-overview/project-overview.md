# 项目概述

> scx-stock-api：统一的股票行情中台后端。

---

## 1. 项目定位

为前端（[scx-gold](https://github.com/shawicx/scx-gold)）提供：

- A 股 / ETF 实时行情（价格、涨跌、换手、主力资金）
- 行业板块涨跌排行与成分股详情
- 大盘指数（上证、深证、创业板等 8 个白名单 + 全部指数分组）
- 黄金品种实时行情（沪金主连、Au99.99、纽约金）
- 代码 / 简称 / 拼音搜索（内存索引，毫秒级）
- 支撑位 / 压力位技术分析 + LLM 智能解读 + 每日邮件报告
- 关注列表管理、应用配置（LLM/SMTP）在线编辑

---

## 2. 技术栈

| 层面 | 选型 |
|------|------|
| 语言 | Python ≥3.13（`requires-python = ">=3.13"`，见 `pyproject.toml`） |
| Web 框架 | FastAPI ≥0.115 + Uvicorn |
| 数据源 | AkShare ≥1.14（东方财富 / 新浪 / 腾讯 / 同花顺多源 fallback） |
| ORM | SQLAlchemy 2.0（async）+ asyncpg |
| 数据库 | PostgreSQL 16（开发期自动建库） |
| 缓存 | Redis ≥5.0（无 Redis 时回退内存缓存） |
| 调度 | APScheduler ≥3.10（AsyncIOScheduler，时区 Asia/Shanghai） |
| 配置 | pydantic-settings ≥2.0（环境变量前缀 `SCX_` + `.env`） |
| 技术指标 | pandas ≥2.0 + pandas-ta |
| LLM | OpenAI ≥1.0（兼容接口，支持 GLM / DeepSeek） |
| 邮件 | aiosmtplib ≥3.0 + Jinja2 ≥3.1 |
| 拼音 | pypinyin ≥0.51 |
| 包管理 | uv（锁文件 `uv.lock`） |
| 构建 | hatchling |

---

## 3. 应用形态

单体后端，单进程（`scx_stock/main.py:app`）。无微服务拆分，无消息队列。后台任务由 APScheduler 在同一事件循环内调度。

---

## 4. 配套前端

[scx-gold](https://github.com/shawicx/scx-gold)：React SPA，通过 nginx 反代访问本后端 `/api/*`。联调详见 [09-frontend-integration](../09-frontend-integration/frontend-guide.md)。

---

## Related

- [架构分层](architecture.md)
- [快速上手](../02-getting-started/quick-start.md)
- [目录结构](../03-codebase/codebase.md)
