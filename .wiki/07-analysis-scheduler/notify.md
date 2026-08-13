# 邮件通知

> aiosmtplib 异步发送每日分析报告，Jinja2 模板渲染。SMTP 配置动态读取。

源码：`scx_stock/notify/email_sender.py`、`scx_stock/notify/templates/daily_report.html`。

---

## 1. 关键函数（`email_sender.py`）

| 函数 | 说明 |
|------|------|
| `render_daily_report(reports, report_date=None)`（`:66`） | 读 `smtp_from_name` 动态配置；渲染 `daily_report.html` |
| `_report_to_template_item`（`:42`） | AnalysisReport → 模板字典；`_format_pct`（`:31`）渲染 `+x.xx`/`-x.xx`，None → `"-"` |
| `build_message(html, recipients)`（`:87`） | `MIMEMultipart("alternative")`；Subject `【每日支撑位分析】YYYY-MM-DD`；`From` 用 `formataddr`（RFC2047 编码中文名避免 QQ 550）；纯文本 + HTML 双部分 |
| `send_email(recipients, html, retries=2)`（`:112`） | 异步发送，最多 3 次尝试 |

---

## 2. send_email 流程

```text
send_email(recipients, html, retries=2):
  1. 动态读 smtp_host/port/user/password/use_ssl
     - smtp_use_ssl 可接受 bool 或字符串("true"/"1"/"yes")
  2. host/user 空 → return (False, "SMTP 主机或账号未配置")
  3. recipients 空 → return (False, "收件人列表为空")
  4. 加密方式由【端口】决定，不由 use_ssl 决定：
     - port 465 → 隐式 TLS（connect(use_tls=True)）
     - 其他（587 等）→ STARTTLS（connect(use_tls=False, start_tls=True)）
  5. 重试 range(1, retries+2) → 最多 3 次
     - 失败 sleep(2*attempt) 秒
     - 全败 → return (False, "TypeName: error")
```

> **注意**：加密选择依据端口（465→TLS，587→STARTTLS），`smtp_use_ssl` 仅作为标记存 DB，实际不决定加密方式。

---

## 3. 邮件模板（`templates/daily_report.html`）

600px 宽卡片布局，`#f5f5f5` 背景，蓝色 `#1a73e8` 头部。

### 模板变量

| 变量 | 说明 |
|------|------|
| `report_date` | 报告日期 |
| `total` / `success` / `failed` | 统计计数 |
| `from_name` | 发件人名（动态 `smtp_from_name`） |
| `items[]` | 每标的分析卡片 |

### `items[]` 每项字段

| 字段 | 说明 |
|------|------|
| `code` / `name` | 代码/简称 |
| `ok` / `error` | 是否成功/错误信息 |
| `trend` | 趋势（失败时显示红色"分析失败"） |
| `close` / `change_pct` | 收盘价/涨跌幅（红涨绿跌） |
| `support_1_price` / `support_1_pct` | 第一支撑（绿色） |
| `support_2_price` / `support_2_pct` | 第二支撑（绿色） |
| `resistance_1_price` / `resistance_1_pct` | 第一压力（红色） |
| `summary` | AI 摘要（灰色框） |

---

## 4. 触发时机

```text
scheduler daily_analysis_job（每日 21:00，非交易日跳过）
  → run_daily_analysis(dry_run=False)
    → 成功报告数 > 0 且有收件人
      → render_daily_report(reports)
      → send_email(recipients, html)
```

收件人来源：动态配置 `notify_emails`（DB > `.env`），逗号分隔。无收件人则 warn 不发。

---

## Related

- [分析引擎](analysis-engine.md)
- [LLM 解读](llm-interpret.md)
- [调度任务](scheduler.md)
- [应用配置接口](../05-api/settings.md)
- [环境变量（SMTP）](../08-configuration/environment-variables.md)
