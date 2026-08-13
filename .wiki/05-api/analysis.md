# 支撑位分析接口

> 手动触发分析、查询最新/历史/按日期报告。需认证。`POST /analysis/run` 受限流（`ai_rate_limit`）。

源码：`scx_stock/api/v1/analysis.py`、`scx_stock/schema/analysis.py`、`scx_stock/scheduler/analysis_job.py`。

---

## 1. `POST /api/v1/analysis/run` — 手动触发分析

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `dry_run` | query | `false` | true 时只分析不发邮件（仍落库） |
| `codes` | query | `None` | 逗号分隔代码；缺省用 DB 关注列表 → `SCX_WATCHLIST` |

**响应 `data`**：

```json
{
  "analyzed": 4, "success": 4, "failed": 0, "sent": 1,
  "reports": [ ... ],
  "elapsed": 12.3
}
```

> - 分析流程：交易日门控（非交易日 `daily_analysis_job` 跳过，但手动 `run` 不受门控）→ 逐 code 读 DB K线（不足 fallback Provider 并回填）→ `analyze()` → LLM 解读 → 落库 → 邮件
> - 详见 [分析引擎](../07-analysis-scheduler/analysis-engine.md)

---

## 2. `GET /api/v1/analysis/latest` — 最新报告

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `codes` | query | `None` | 逗号分隔代码；缺省返回全部最新 |

**响应 `data`**：`list[AnalysisReport]`

---

## 3. `GET /api/v1/analysis/history` — 标的历史报告

| 参数 | 位置 | 默认 | 约束 | 说明 |
|------|------|------|------|------|
| `code` | query | 必填 | — | 股票/ETF 代码 |
| `limit` | query | `30` | `ge=1, le=365` | 返回条数 |

**响应 `data`**：`list[AnalysisReport]`（按日期降序）

---

## 4. `GET /api/v1/analysis/report/{trade_date}` — 按日期查询

| 参数 | 位置 | 说明 |
|------|------|------|
| `trade_date` | path | 日期 `YYYY-MM-DD` |

**响应 `data`**：`list[AnalysisReport]`

---

## 5. AnalysisReport 结构（`schema/analysis.py:25`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | str | 代码 |
| `name` | str | 简称（默认 `""`） |
| `trade_date` | date\|null | 交易日 |
| `close` | float\|null | 收盘价 |
| `change_pct` | float\|null | 涨跌幅 |
| `support_1` | SupportLevel\|null | 第一支撑位 |
| `support_2` | SupportLevel\|null | 第二支撑位 |
| `resistance_1` | SupportLevel\|null | 第一压力位 |
| `trend` | str | 趋势：多头/空头/震荡/未知/数据不足 |
| `ma20` | float\|null | MA20 |
| `ma60` | float\|null | MA60 |
| `summary` | str | AI 解读摘要（LLM 失败时为规则模板） |
| `ok` | bool | 分析是否成功（默认 true） |
| `error` | str | 失败原因（默认 `""`） |

### SupportLevel 结构（`schema/analysis.py:10`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `price` | float | 价位 |
| `sources` | list[str] | 来源标签（如 `["MA20","Pivot S1"]`） |
| `distance_pct` | float | 距现价百分比（支撑为负，压力为正） |
| `strength` | str | 强度：强（≥3源）/中（2源）/弱（1源），默认 `中` |

---

## Related

- [分析引擎详解](../07-analysis-scheduler/analysis-engine.md)
- [LLM 解读](../07-analysis-scheduler/llm-interpret.md)
- [调度任务](../07-analysis-scheduler/scheduler.md)
- [API 总览](overview.md)
