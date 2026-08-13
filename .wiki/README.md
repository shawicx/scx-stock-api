# scx-stock-api Wiki

> 统一的 A 股 / ETF / 黄金行情中台后端，基于 FastAPI + AkShare，提供实时行情、板块指数、支撑位 AI 分析与每日邮件报告。

本 Wiki 基于真实源码生成，所有代码引用指向仓库相对路径。

---

## 按角色阅读

**新人上手**：`01-overview` → `02-getting-started` → `03-codebase` → `11-development`

**前端联调**：`09-frontend-integration` → `05-api`

**AI Agent 改代码**：`03-codebase` → `04-data-providers` → `06-data` → `07-analysis-scheduler`

**运维部署**：`10-deployment` → `08-configuration`

---

## 核心导航

| 章节 | 内容 |
|------|------|
| [01-overview](01-overview/project-overview.md) | 项目定位、技术栈、架构分层 |
| [02-getting-started](02-getting-started/quick-start.md) | 环境准备、启动、首次同步 |
| [03-codebase](03-codebase/codebase.md) | 完整目录树与各包职责 |
| [04-data-providers](04-data-providers/fallback.md) | 多源 fallback 机制（核心难点）、缓存策略 |
| [05-api](05-api/overview.md) | 全部 HTTP 端点（29 个） |
| [06-data](06-data/data-model.md) | 8 张 ORM 表、持久化策略 |
| [07-analysis-scheduler](07-analysis-scheduler/analysis-engine.md) | 支撑位分析引擎、LLM 解读、通知、调度 |
| [08-configuration](08-configuration/environment-variables.md) | 配置项全量、动态配置机制 |
| [09-frontend-integration](09-frontend-integration/frontend-guide.md) | 前端联调指南 |
| [10-deployment](10-deployment/deployment.md) | CI/CD、Docker、阿里云 ECS 部署 |
| [11-development](11-development/development.md) | 测试、调试、编码规范 |

---

## 配套项目

- 前端：[scx-gold](https://github.com/shawicx/scx-gold)（React 涨停候选筛选器 + 每日分析报告页）

## 关联文档

- 项目规范：[`AGENTS.md`](../AGENTS.md)（AI 代码修改强制规则）
- OpenAPI：启动后访问 `http://localhost:8000/docs`（Swagger UI）
