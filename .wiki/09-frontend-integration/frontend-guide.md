# 前端联调指南

> 面向 [scx-gold](https://github.com/shawicx/scx-gold) 及其他前端，说明如何对接本后端。

---

## 1. 启动后端

```bash
cp .env.example .env       # 按需修改配置
uv run uvicorn scx_stock.main:app --reload --port 8000
```

启动后默认地址：

- API: http://localhost:8000
- Swagger UI（交互式文档）: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## 2. CORS 跨域

默认允许的前端开发源（`SCX_CORS_ORIGINS`）：

```
http://localhost:3000 / 127.0.0.1:3000
http://localhost:5173 / 127.0.0.1:5173   (Vite)
http://localhost:8080 / 127.0.0.1:8080
```

- **自定义源**：`.env` 修改 `SCX_CORS_ORIGINS`（逗号分隔）
- **`*` 模式**：允许全部源，但会**关闭 `allow_credentials`**（无法携带 Cookie）

---

## 3. 认证

除 `/health*` 和 `/api/v1/auth/*` 外，所有接口需 `X-Access-Token` 请求头。

```js
const api = axios.create({ baseURL: 'http://localhost:8000' })
api.interceptors.request.use(config => {
  config.headers['X-Access-Token'] = localStorage.getItem('access_token')
  return config
})
```

获取 token 流程：`POST /api/v1/auth/request-code` → 邮箱收 16 位码 → 存 localStorage。详见 [认证机制](../05-api/auth.md)。

---

## 4. 统一响应处理

所有接口统一返回：

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

### axios 拦截器封装

```js
import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 10000,
})

// 请求拦截：注入 token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers['X-Access-Token'] = token
  return config
})

// 响应拦截：解包 data
api.interceptors.response.use(
  res => {
    if (res.data.code === 0) return res.data.data   // 成功直接返回 data
    return Promise.reject(new Error(res.data.message))
  },
  err => {
    // 429 附 Retry-After 头（秒）
    if (err.response?.status === 429) {
      const retry = err.response.headers['retry-after']
      return Promise.reject(new Error(`请求过频，${retry}秒后重试`))
    }
    const msg = err.response?.data?.message || err.message
    return Promise.reject(new Error(msg))
  }
)

// 使用（已解包，无需 .data.data）
const list = await api.get('/api/v1/stock/list', { params: { page: 1, page_size: 20 } })
```

### 错误码

| code | HTTP | 含义 |
|------|------|------|
| 0 | 200 | 成功 |
| 40001 | 400 | 业务校验失败 |
| 40401 | 404 | 资源不存在 |
| 42201 | 422 | 参数校验失败 |
| 42901 | 429 | 限流（读 `Retry-After` 头倒计时） |
| 50001 | 500 | 服务异常 |
| 50201 | 502 | 数据源异常（建议重试 1~2 次） |

---

## 5. 按业务域的接口调用

| 业务 | 端点 | 文档 |
|------|------|------|
| 行情列表 | `GET /api/v1/stock/list` | [quotes](../05-api/quotes.md) |
| 个股详情 | `GET /api/v1/stock/{code}` | [quotes](../05-api/quotes.md) |
| 搜索 | `GET /api/v1/search?q=` | [quotes](../05-api/quotes.md) |
| 板块排行 | `GET /api/v1/sector/list` | [sectors-indexes-gold](../05-api/sectors-indexes-gold.md) |
| 板块详情 | `GET /api/v1/sector/{name}` | [sectors-indexes-gold](../05-api/sectors-indexes-gold.md) |
| 主要指数 | `GET /api/v1/market/index` | [sectors-indexes-gold](../05-api/sectors-indexes-gold.md) |
| 黄金 | `GET /api/v1/market/gold` | [sectors-indexes-gold](../05-api/sectors-indexes-gold.md) |
| 分析报告 | `GET /api/v1/analysis/latest` | [analysis](../05-api/analysis.md) |
| 关注列表 | `GET/POST/PUT/DELETE /api/v1/watchlist` | [watchlist](../05-api/watchlist.md) |
| 应用配置 | `GET/PUT /api/v1/settings` | [settings](../05-api/settings.md) |
| 健康检查 | `GET /health/ready` | [health-admin](../05-api/health-admin.md) |
| 手动同步 | `POST /admin/sync` | [health-admin](../05-api/health-admin.md) |

---

## 6. 注意事项

- **个股端点仅支持 A 股**：代码正则 `^[0368]\d{4,5}$`；ETF 详情暂不支持
- **搜索为空不报错**：索引未构建时返回 `{code:0, data:[]}`，可调 `POST /admin/reindex`
- **实时行情有缓存**：列表 120s / 个股 30s TTL
- **数据源字段差异**：
  - 东方财富：字段最全
  - 新浪：缺换手率/主力资金
  - 腾讯：含换手率+主力资金，缺高低价
  - `main_net_inflow` / `industry` 等可能为 `null`
- **数据源不稳定**：后端有多源 fallback，但仍可能返回 50201，建议前端重试 1~2 次
- **限流**：`POST /analysis/run`、`POST /settings/test-llm|test-smtp` 受限流（20 次/分钟），429 时读 `Retry-After` 头
- **配置即时生效**：前端 `/settings` 修改 LLM/SMTP 后无需重启后端

---

## 7. 联调流程

```text
1. GET /health/ready              确认后端依赖正常
2. POST /api/v1/auth/request-code 获取授权码（邮件）
3. POST /admin/sync               首次同步（让搜索可用），轮询 /admin/task/{id}
4. GET /api/v1/search?q=510300    验证搜索
5. GET /api/v1/stock/list         验证行情
```

---

## Related

- [API 总览](../05-api/overview.md)
- [认证机制](../05-api/auth.md)
- [快速上手](../02-getting-started/quick-start.md)
