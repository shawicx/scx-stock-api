# LLM 智能解读

> 将结构化分析结果交给 LLM 生成中文摘要，失败自动降级为规则模板。

源码：`scx_stock/llm/client.py`、`scx_stock/llm/interpreter.py`。

---

## 1. 客户端（`client.py`）

OpenAI 兼容异步客户端（`AsyncOpenAI`）。**配置每次调用动态读取**（DB `app_setting` > `.env`），改配置即时生效无需重启。

### 1.1 厂商默认（`_PROVIDER_DEFAULTS`，`client.py:17`）

| provider | base_url | model |
|----------|----------|-------|
| `deepseek` | `https://api.deepseek.com/v1` | `deepseek-chat` |
| `glm` | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |

### 1.2 关键方法

| 方法 | 说明 |
|------|------|
| `_get_config()`（`:35`） | 读 `llm_provider/api_key/base_url/model/timeout`；base_url/model 空时用厂商默认 |
| `available()`（`:53`） | `llm_api_key` 非空 → True |
| `chat(system, user, max_tokens=1024)`（`:61`） | `temperature=0.3`；无 key 抛 `RuntimeError`；返回 stripped content；`finish_reason=="length"` 时 warn |
| `get_llm_client()`（`:110`） | 单例 |

---

## 2. 解读（`interpreter.py:64` `interpret(report)`）

回填 `report.summary`，**永不抛异常**：

```text
1. report.ok == False          → fallback_summary
2. client.available() == False → fallback_summary（日志 "LLM 未配置"）
3. chat(system=_SYSTEM_PROMPT, user=_build_user_prompt(report), max_tokens=1024)
   - 返回空  → fallback_summary
   - 抛异常  → warn + fallback_summary
   - 正常    → 使用 LLM 返回文本
```

### 2.1 System Prompt（`interpreter.py`）

要求模型作为 ETF/股票技术分析师：
- 输出 150–250 字中文摘要
- **只用提供的数字，不编造**
- 综合趋势、均线、量能（量比）与动量（MACD/RSI/KDJ）；信号方向不一致时须指出并解释
- 覆盖趋势与动量状态、支撑/压力、明日关注点
- 附免责声明
- 不用 Markdown 标题

### 2.2 User Prompt（`_build_user_prompt`）

序列化：name、code、date、close、当日/近5日/近20日涨跌幅、trend（含 `trend_note` 备注）、MA20/MA60、量比、RSI(14)、MACD（DIF/DEA/柱）、KDJ J 值，以及每个支撑/压力位的 price/distance_pct/sources/strength。

---

## 3. 配置

LLM 配置通过前端 `/settings` 页或 `.env` 管理，详见：

- [环境变量](../08-configuration/environment-variables.md)（`SCX_LLM_*`）
- [动态配置](../08-configuration/dynamic-config.md)
- [应用配置接口](../05-api/settings.md)

---

## Related

- [分析引擎](analysis-engine.md)
- [通知（邮件）](notify.md)
- [应用配置接口](../05-api/settings.md)
