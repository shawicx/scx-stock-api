# 应用配置接口

> 在线查看/修改 LLM、SMTP 与授权码配置，测试连通性。需认证。`test-llm` / `test-smtp` 受限流。

源码：`scx_stock/api/v1/settings.py`、`scx_stock/config/dynamic.py`、`scx_stock/storage/repo.py`（settings 系列）。

---

## 1. `GET /api/v1/settings` — 获取配置

无参数。

**响应 `data`**：`dict[str, str]`，包含 13 个动态配置键。

**敏感字段脱敏**（`settings.py:_mask`）：

- `llm_api_key`、`smtp_password` 脱敏：前 3 + `***` + 后 4（长度 ≤ 7 显示 `***`，空值原样返回）

配置键（`dynamic.py:_SETTING_KEYS`）：

| 键 | 说明 |
|----|------|
| `llm_provider` | LLM 厂商（glm / deepseek） |
| `llm_api_key` | API Key（脱敏） |
| `llm_base_url` | 接口地址 |
| `llm_model` | 模型名 |
| `llm_timeout` | 超时秒 |
| `smtp_host` | SMTP 主机 |
| `smtp_port` | 端口 |
| `smtp_user` | 账号 |
| `smtp_password` | 密码/授权码（脱敏） |
| `smtp_from_name` | 发件人名称 |
| `smtp_use_ssl` | 是否 SSL |
| `notify_emails` | 每日报告收件人（逗号分隔） |
| `auth_code_ttl_hours` | 授权码有效期（小时），默认 72（3 天） |

---

## 2. `PUT /api/v1/settings` — 更新配置

**请求体**：`SettingsUpdate`（所有字段可选 `str|None`，`None`/缺省表示不更新）

键同上表。

**响应 `data`**：`{updated: int}`（更新行数）

> 写入 DB `app_setting` 表，下次读取即时生效，无需重启。详见 [动态配置](../08-configuration/dynamic-config.md)。

---

## 3. `POST /api/v1/settings/test-llm` — 测试 LLM 连接

无参数（使用当前动态配置）。受限流（`ai_rate_limit`）。

**响应 `data`**：`{success: bool, message: str, reply: str}`

---

## 4. `POST /api/v1/settings/test-smtp` — 测试 SMTP 发信

无参数（使用当前动态配置）。受限流（`ai_rate_limit`）。

**响应 `data`**：`{success: bool, message: str}`

---

## 5. 配置优先级

```text
读取（get_dynamic_setting）：
  DB app_setting 表  →  .env (Settings)  →  默认值

写入（PUT /settings）：
  只写 DB app_setting 表（不写 .env）
```

> 因此 `.env` 是兜底默认值；前端修改后 DB 值覆盖之，永久生效（直到 DB 值被再次修改或删除）。

---

## Related

- [动态配置机制](../08-configuration/dynamic-config.md)
- [环境变量全量](../08-configuration/environment-variables.md)
- [LLM 解读](../07-analysis-scheduler/llm-interpret.md)
- [通知（SMTP）](../07-analysis-scheduler/notify.md)
- [API 总览](overview.md)
