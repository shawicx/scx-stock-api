# 动态配置机制

> LLM / SMTP 配置支持运行时修改，DB 优先、`.env` 回退，前端改动即时生效无需重启。

源码：`scx_stock/config/dynamic.py`、`scx_stock/storage/repo.py`（app_setting 系列）。

---

## 1. 优先级

```text
读取（get_dynamic_setting / get_dynamic_settings）：
  DB app_setting 表  →  .env (Settings 字段)  →  默认值

写入（PUT /api/v1/settings）：
  只写 DB app_setting 表（不写 .env）
```

- DB 有该键 → 用 DB 值
- DB 无该键 → 回退 `.env` 中 `SCX_LLM_*` / `SCX_SMTP_*` 等
- 都没有 → 用代码默认

> 因此前端修改后，DB 值覆盖 `.env`，**永久生效**（直到 DB 值被再次修改或从表中删除）。

---

## 2. 动态配置键（12 个）

`dynamic.py:_SETTING_KEYS`（`:17`）：

**LLM（5）**：`llm_provider`、`llm_api_key`、`llm_base_url`、`llm_model`、`llm_timeout`

**SMTP（6）**：`smtp_host`、`smtp_port`、`smtp_user`、`smtp_password`、`smtp_from_name`、`smtp_use_ssl`

**通知（1）**：`notify_emails`

> 这些键同时存在于 `Settings`（`.env` 的 `SCX_` 前缀去掉即键名），保证回退链完整。

---

## 3. 关键函数

| 函数 | 说明 |
|------|------|
| `get_dynamic_setting(key, default=None)`（`:33`） | 单键读取：DB → Settings → default；DB 错误不抛 |
| `get_dynamic_settings(keys=None)`（`:56`） | 批量读取：`None` 读全部 12 键，合并 DB-over-`.env` |

---

## 4. 谁在用动态配置

| 消费方 | 读取时机 | 用途 |
|--------|---------|------|
| `llm/client.py:_get_config` | **每次 chat 调用** | LLM 厂商/key/url/model/timeout |
| `notify/email_sender.py:send_email` | **每次发信** | SMTP host/port/user/password/use_ssl |
| `notify/email_sender.py:render_daily_report` | 每次渲染 | `smtp_from_name` |
| `scheduler/analysis_job.py:run_daily_analysis` | 每次分析 | `notify_emails`（收件人） |

> 因为每次调用都动态读取，前端 `/settings` 修改后**无需重启**即生效。

---

## 5. 修改方式

```text
前端 PUT /api/v1/settings  →  repo.upsert_settings  →  DB app_setting 表
                                     ↓
下次 LLM/SMTP/邮件消费时  ←  get_dynamic_settings  ←  DB
```

- 敏感字段（`llm_api_key`、`smtp_password`）：GET 时脱敏（前 3 + `***` + 后 4）
- PUT 时 `None`/缺省字段不更新

详见 [应用配置接口](../05-api/settings.md)。

---

## Related

- [环境变量全量](environment-variables.md)
- [应用配置接口](../05-api/settings.md)
- [LLM 解读](../07-analysis-scheduler/llm-interpret.md)
- [邮件通知](../07-analysis-scheduler/notify.md)
