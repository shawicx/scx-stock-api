# 认证机制

> 授权码认证：请求码 → 邮件 → 验证 → token。支持固定测试 token。`/api/v1/auth/*` 公开无需认证。

源码：`scx_stock/middleware/auth.py`、`scx_stock/api/v1/auth.py`、`scx_stock/storage/repo.py`（auth_code 系列）、`scx_stock/storage/models.py`（`AuthCodeModel`）。

---

## 1. 认证流程

```text
① 客户端 POST /api/v1/auth/request-code
     → 生成 16 位授权码（大写字母+数字）
     → 存 DB auth_code 表（is_active=true, expires_at=now+24h）
     → 邮件发送给 SCX_NOTIFY_EMAILS（+ 一个硬编码兜底邮箱）

② 客户端从邮箱拿到码，后续请求带 header：
     X-Access-Token: <16位码>
   或
     Authorization: Bearer <16位码>

③ 服务端 require_access_token 校验：
     - 缺 token → 401 "缺少授权码"
     - 匹配 SCX_TEST_TOKEN（若配置）→ 通过
     - 否则 DB 查 auth_code：存在 + is_active + 未过期 → 通过
     - 否则 → 401 "授权码无效或已过期"

④ POST /api/v1/auth/logout（可选）
     → deactivate_auth_code：is_active=false
```

---

## 2. 端点（`/api/v1/auth/*`，公开）

### `POST /api/v1/auth/request-code`

无参数。

**响应 `data`**：`{sent: bool, message?: str}`

> 即使邮件发送失败，授权码已存入 DB（仍可用）。

### `POST /api/v1/auth/verify`

**请求体**：`{code: str}`（`min_length=16, max_length=16`）

**响应 `data`**：`{valid: bool, message?: str}`

### `POST /api/v1/auth/logout`

**请求体**（可选）：`{code: str}`（`min_length=16, max_length=16`）

**响应 `data`**：`{done: bool}`（恒 true）

> 提供 code 时停用该码（`is_active=false`）。

---

## 3. 授权码规格

| 属性 | 值 |
|------|-----|
| 字符集 | `string.ascii_uppercase + string.digits`（避开易混淆字符） |
| 长度 | 16 位 |
| 生成 | `secrets.choice`（密码学安全随机） |
| TTL | 24 小时（`_CODE_TTL_HOURS=24`，`auth.py:23`） |
| 存储 | DB `auth_code` 表（PK=code，`is_active` 索引） |
| 失效 | `expires_at < now` 或 `is_active=false` 或不存在 |
| DB 错误 | fail-closed（`validate_auth_code` 返回 False） |

---

## 4. 固定测试 token（开发/测试）

`.env` 设置 `SCX_TEST_TOKEN=xxx` 后，请求头 `X-Access-Token: xxx` 直接通过，无需走授权码流程。生产环境留空即可走授权码认证。

校验优先级（`middleware/auth.py:47`）：**test_token 优先于动态授权码**。

---

## 5. 待确认项

- `api/v1/auth.py:26` 存在一个硬编码兜底收件邮箱（`_NOTIFY_EMAIL`），授权码邮件会额外发给该邮箱。**待确认**：该邮箱是否应为生产配置（建议改为环境变量）。

---

## Related

- [API 总览](overview.md)
- [环境变量](../08-configuration/environment-variables.md)
- [通知（邮件）](../07-analysis-scheduler/notify.md)
- [数据模型（auth_code 表）](../06-data/data-model.md)
