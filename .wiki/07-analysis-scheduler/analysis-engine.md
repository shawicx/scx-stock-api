# 支撑位分析引擎

> K 线 → 技术指标 → 支撑/压力候选 → 聚类打分 → 趋势 → 结构化报告。

源码：`scx_stock/analysis/indicators.py`、`support.py`、`trend.py`、`engine.py`、`scx_stock/schema/analysis.py`。

---

## 1. 分析管线（`engine.py:19` `analyze(kline)`）

```text
输入：Kline（KlineBar 列表）
  ↓
1. 校验：len(bars) >= 30，否则返回 AnalysisReport(ok=False, error=...)
  ↓
2. to_dataframe(bars) → DataFrame（date/close/high/low/volume）
   current_price = close.iloc[-1]
   change_pct = (current - prev_close) / prev_close * 100
  ↓
3. find_supports(df, current_price, top_n=2)   → support_1, support_2
   find_resistances(df, current_price, top_n=1) → resistance_1
  ↓
4. judge_trend(close) → trend（多头/空头/震荡）
  ↓
5. ma20 = calc_ma(close, 20), ma60 = calc_ma(close, 60)
  ↓
输出：AnalysisReport(summary="")  # summary 由 LLM 后续填充
```

---

## 2. 技术指标（`indicators.py`）

| 函数 | 说明 | 参数 |
|------|------|------|
| `calc_ma(close, period)` | 简单移动平均最新值（`ta.sma`） | 数据不足返回 None |
| `calc_boll_lower(close)` | 布林下轨（`ta.bbands length=20, std=2`，读 `BBL_20_2.0`） | |
| `calc_pivot_points(high, low, close)` | 经典枢轴点（前日 H/L/C） | pivot/r1/r2/s1/s2，4 位小数 |
| `calc_recent_low(df, days)` | 最近 N 日最低 | 取 `df["low"]` 末尾 days 行 min |
| `calc_recent_high(df, days)` | 最近 N 日最高 | |
| `to_dataframe(bars)` | KlineBar → DataFrame（按日期升序） | 列：date/close/high/low/volume |

### Pivot 公式

```text
pivot = (H + L + C) / 3
r1 = 2*pivot - low      s1 = 2*pivot - high
r2 = pivot + (high-low)  s2 = pivot - (high-low)
```

---

## 3. 支撑/压力位（`support.py`）

### 3.1 候选收集（`_collect_candidates`，`support.py:26`）

收集 `(price, source_label)` 元组：

| 来源 | 标签 |
|------|------|
| MA20 / MA60 / MA120 | `MA20` / `MA60` / `MA120` |
| 布林下轨 | `BOLL下轨` |
| Pivot S1 / S2 / R1 / R2（取 `df.iloc[-2]` 前日） | `Pivot S1/S2/R1/R2` |
| 20 日低点 / 60 日低点 | `20日低点` / `60日低点` |
| 20 日高点 / 60 日高点 | `20日高点` / `60日高点` |

### 3.2 聚类（`_cluster`，`support.py:73`）

- **容差**：`_CLUSTER_TOLERANCE = 0.01`（**1%**，`support.py:23`）——价位在簇中心 1% 内则合并
- 支撑：保留 `price < current_price`；压力：保留 `price > current_price`
- 按距现价排序（近的在前）
- 合并：簇中心 = (原中心 + 新价) / 2（4 位小数），source 标签追加到列表

### 3.3 强度（`_strength_label`，`support.py:116`）

| 来源数 | 强度 |
|--------|------|
| ≥ 3 | `强` |
| = 2 | `中` |
| 其他 | `弱` |

### 3.4 入口

- `find_supports(df, current_price, top_n=2)` → `support.py:129`，`distance_pct` 为负
- `find_resistances(df, current_price, top_n=1)` → `support.py:155`，`distance_pct` 为正
- `distance_pct = (price - current_price) / current_price * 100`（2 位小数）

---

## 4. 趋势判断（`trend.py:10` `judge_trend`）

| 条件 | 趋势 |
|------|------|
| `close > MA20 > MA60` | `多头` |
| `close < MA20 < MA60` | `空头` |
| 其他 | `震荡` |
| 空序列 | `未知` |
| MA 数据不足 | `数据不足` |

---

## 5. 降级摘要（`engine.py:72` `fallback_summary`）

LLM 不可用时用规则模板拼接：趋势 + MA20 位置 + 支撑/压力价位。

---

## 6. 输出结构

见 [AnalysisReport 字段](../05-api/analysis.md#5-analysisreport-结构schemaanalysipy25)。

---

## Related

- [LLM 解读](llm-interpret.md)
- [调度任务](scheduler.md)
- [分析接口](../05-api/analysis.md)
- [K 线存储](../06-data/storage.md)
