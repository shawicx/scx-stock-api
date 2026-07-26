# 前端联调指南

> 本文档面向前端开发者，说明如何与 scx-stock-api 后端对接。

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

后端已启用 CORS。默认允许以下前端开发源：

```
http://localhost:3000
http://127.0.0.1:3000
http://localhost:5173
http://127.0.0.1:5173
http://localhost:8080
http://127.0.0.1:8080
```

**自定义源**：修改 `.env` 中的 `SCX_CORS_ORIGINS`（逗号分隔），设为 `*` 表示允许所有源（仅本地调试）。

```bash
# 例：允许 Vite 默认端口 + 自定义前端域名
SCX_CORS_ORIGINS=http://localhost:5173,https://stock.example.com
```

> 注意：当 `SCX_CORS_ORIGINS=*` 时，后端会关闭 `allow_credentials`，前端无法携带 Cookie。
> 需要携带凭证时，请显式列出源，不要用 `*`。

---

## 3. 统一响应格式

所有接口（成功与错误）统一返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | 业务码，**0 = 成功**，非 0 = 业务错误 |
| `message` | string | 描述信息，成功为 `"ok"` |
| `data` | any | 业务数据，错误时为 `null` |

### 前端判断逻辑

```js
// 推荐判断方式（双重保险）
if (res.status >= 200 && res.status < 300 && res.data.code === 0) {
  // 成功，使用 res.data.data
} else {
  // 失败，展示 res.data.message
}
```

> HTTP 状态码同步保持语义（200/400/404/422/502/500），前端可二选一判断。

### 错误响应示例

参数校验失败（HTTP 422）：
```json
{
  "code": 42201,
  "message": "请求参数校验失败",
  "data": [
    { "loc": ["query", "q"], "msg": "ensure this value has at least 1 characters" }
  ]
}
```

资源不存在（HTTP 404）：
```json
{ "code": 40401, "message": "stock not found: 999999", "data": null }
```

数据源异常（HTTP 502）：
```json
{ "code": 50201, "message": "数据源异常: ...", "data": null }
```

### 错误码对照

| code | HTTP | 含义 |
|------|------|------|
| 0 | 200 | 成功 |
| 40001 | 400 | 业务校验失败 |
| 40401 | 404 | 资源不存在 |
| 42201 | 422 | 请求参数校验失败（FastAPI 自动） |
| 50001 | 500 | 服务异常 |
| 50201 | 502 | 数据源异常（上游不可用） |

---

## 4. 可用接口

完整契约见 `/docs`，核心接口如下。

### 4.1 股票/ETF 行情列表

```
GET /api/v1/stock/list
```

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `market` | query | `全部` | 市场板块：上证/深证/创业板/科创板/北交所/全部 |
| `type` | query | `stock` | 证券类型：stock/etf/all |
| `sort_by` | query | `change_pct` | 排序字段：change_pct/amount/turnover_rate |
| `descending` | query | `true` | 是否降序 |
| `page` | query | `1` | 页码（从 1 起） |
| `page_size` | query | `20` | 每页条数（1~100） |

成功 `data`：
```json
{
  "items": [
    {
      "code": "600519", "name": "贵州茅台", "market": "上证",
      "price": 1800.0, "change": 10.0, "change_pct": 0.56,
      "amount": 1000000000, "volume": 123456, "turnover_rate": 0.5,
      "high": 1810.0, "low": 1785.0, "open": 1795.0, "prev_close": 1790.0
    }
  ],
  "total": 5000, "page": 1, "page_size": 20
}
```

> 限制：
> - `type=etf` 时忽略 `market`（ETF 不按板块细分）。
> - `market=北交所` 在当前数据源（`stock_zh_a_spot_em`）下可能返回空，属预期行为。
> - 行情数据有 120 秒缓存，短时间内重复请求命中缓存。

### 4.2 个股详情

```
GET /api/v1/stock/{code}
```

| 参数 | 位置 | 说明 |
|------|------|------|
| `code` | path | A 股代码（6 位，首位 0/3/6/8） |

成功 `data`：
```json
{
  "info": { "code": "600519", "name": "贵州茅台", "market": "上证", "industry": "..." },
  "quote": {
    "code": "600519", "name": "贵州茅台",
    "price": 1800.0, "prev_close": 1790.0,
    "change": 10.0, "change_pct": 0.56,
    "volume": 123456, "amount": 1000000,
    "high": 1810.0, "low": 1785.0, "open": 1795.0,
    "timestamp": "2026-07-25T10:00:00"
  },
  "fetched_at": "2026-07-25T10:00:00"
}
```

> 限制：当前仅支持 A 股个股代码。ETF / 美股 / 港股由其他端点提供（待实现）。

### 4.3 搜索

```
GET /api/v1/search?q={keyword}&limit={limit}
```

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `q` | query | 必填 | 关键词（代码 / 简称 / 拼音首字母） |
| `limit` | query | 20 | 最大返回数（1~100） |

成功 `data`（按相关度降序）：
```json
[
  { "code": "600519", "name": "贵州茅台", "market": "上证", "type": "stock", "score": 100 },
  { "code": "510300", "name": "沪深300ETF", "market": "上证", "type": "etf", "score": 80 }
]
```

搜索维度：
- 精确代码（`600519`）
- 简称包含（`茅台`）
- 拼音全拼（`guizhou`）
- 拼音首字母（`gzmt`）

> 注：搜索依赖内存索引，索引由定时任务每日 09:00 构建。索引为空时返回 `[]`，
> 可调用 `POST /admin/sync` 手动触发首次同步。

### 4.4 索引大小（运维）

```
GET /api/v1/search/index-size
```

### 4.5 健康检查

```
GET /health          存活探针（进程在跑即 ok）
GET /health/ready    就绪探针（检查缓存 / DB 依赖）
```

就绪探针 `data`：
```json
{
  "status": "ok",
  "checks": {
    "cache": "ok",
    "db": "ok (5234 rows)"
  }
}
```

### 4.6 运维端点

```
POST /admin/sync       手动触发：股票列表 → ETF 列表 → 重建索引
POST /admin/reindex    仅从 DB 重建搜索索引
```

---

## 5. 前端联调建议

### 5.1 开发流程

1. **先调通健康检查**：`GET /health/ready` 确认后端依赖正常
2. **首次同步索引**：`POST /admin/sync`（DB 就绪后），让搜索可用
3. **验证搜索**：`GET /api/v1/search?q=600519`
4. **验证个股**：`GET /api/v1/stock/600519`

### 5.2 axios 封装示例

```js
import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:8000', timeout: 10000 })

// 统一响应拦截
api.interceptors.response.use(
  (res) => {
    if (res.data.code === 0) return res.data.data   // 成功直接返回 data
    return Promise.reject(new Error(res.data.message))
  },
  (err) => {
    const msg = err.response?.data?.message || err.message
    return Promise.reject(new Error(msg))
  }
)

// 使用
const detail = await api.get('/api/v1/stock/600519')
// detail 即响应中的 data 字段，无需再 .data.data
```

### 5.3 注意事项

- **个股端点仅支持 A 股**：代码正则 `^[0368]\d{4,5}$`，其他格式返回 40001
- **搜索为空不报错**：索引未构建时返回 `{code:0, data:[]}`，需先同步
- **实时行情有缓存**：30 秒 TTL，同一代码短时间重复请求会命中缓存
- **数据源不稳定**：AkShare 底层抓东方财富，可能因网络波动返回 50201，前端建议重试 1~2 次

---

## 6. 当前 API 覆盖范围

| 能力 | 状态 | 端点 |
|------|------|------|
| 股票/ETF 行情列表 | ✅ | `GET /api/v1/stock/list` |
| A 股个股详情 | ✅ | `GET /api/v1/stock/{code}` |
| 搜索（代码/简称/拼音） | ✅ | `GET /api/v1/search` |
| 健康检查 | ✅ | `GET /health`、`GET /health/ready` |
| 运维同步 | ✅ | `POST /admin/sync`、`POST /admin/reindex` |
| ETF 详情 | ⏳ 待实现 | — |
| 板块涨跌 | ⏳ 待实现 | — |
| 主力资金 | ⏳ 待实现 | — |
| 大盘指数 | ⏳ 待实现 | — |
| AI 分析 | ⏳ 待实现 | — |

待实现端点上线后契约保持一致（统一 `{code, message, data}` 格式）。
