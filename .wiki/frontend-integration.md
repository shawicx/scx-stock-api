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
http://localhost:3000 / http://127.0.0.1:3000
http://localhost:5173 / http://127.0.0.1:5173
http://localhost:6900 / http://127.0.0.1:6900
```

**自定义源**：修改 `.env` 中的 `SCX_CORS_ORIGINS`（逗号分隔），设为 `*` 表示允许所有源（仅本地调试）。

> 注意：当 `SCX_CORS_ORIGINS=*` 时，后端会关闭 `allow_credentials`，前端无法携带 Cookie。

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

### 错误码对照

| code | HTTP | 含义 |
|------|------|------|
| 0 | 200 | 成功 |
| 40001 | 400 | 业务校验失败 |
| 40401 | 404 | 资源不存在 |
| 42201 | 422 | 请求参数校验失败（FastAPI 自动） |
| 42901 | 429 | 请求超限流（附 `Retry-After` 响应头，秒数） |
| 50001 | 500 | 服务异常 |
| 50201 | 502 | 数据源异常（上游不可用） |

> 429 响应头含 `Retry-After: 60`，前端应据此做倒计时提示。

---

## 4. 可用接口

### 4.1 股票/ETF 行情列表

```
GET /api/v1/stock/list
```

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `market` | query | `全部` | 市场板块：上证/深证/创业板/科创板/北交所/全部 |
| `type` | query | `stock` | 证券类型：stock/etf/all |
| `sort_by` | query | `change_pct` | 排序字段：change_pct/amount/turnover_rate/**main_net_inflow** |
| `descending` | query | `true` | 是否降序 |
| `page` | query | `1` | 页码（从 1 起，ge=1） |
| `page_size` | query | `20` | 每页条数（1~100） |

成功 `data`：
```json
{
  "items": [
    {
      "code": "600519", "name": "贵州茅台", "market": "上证",
      "price": 1800.0, "change": 10.0, "change_pct": 0.56,
      "amount": 1000000000, "volume": 123456, "turnover_rate": 0.5,
      "high": 1810.0, "low": 1785.0, "open": 1795.0, "prev_close": 1790.0,
      "main_net_inflow": 500000000, "main_net_inflow_pct": 2.5,
      "industry": "白酒"
    }
  ],
  "total": 5400, "page": 1, "page_size": 100
}
```

> - `main_net_inflow` / `main_net_inflow_pct` / `industry` 可能为 `null`（取决于数据源）
> - 行情数据有 120 秒缓存
> - **新源字段差异**：东方财富源字段最全；新浪源缺换手率/主力资金；腾讯源含换手率+主力资金但缺高低价

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
  "info": { "code": "600519", "name": "贵州茅台", "market": "上证", "industry": "白酒" },
  "quote": {
    "code": "600519", "name": "贵州茅台",
    "price": 1800.0, "prev_close": 1790.0,
    "change": 10.0, "change_pct": 0.56,
    "volume": 123456, "amount": 1000000,
    "high": 1810.0, "low": 1785.0, "open": 1795.0,
    "timestamp": "2026-08-09T10:00:00"
  },
  "fetched_at": "2026-08-09T10:00:00"
}
```

> 仅支持 A 股个股代码。ETF 详情待实现。

### 4.3 板块涨跌排行

```
GET /api/v1/sector/list
```

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `sort_by` | query | `change_pct` | 排序：change_pct/turnover_rate/total_market_cap |
| `descending` | query | `true` | 是否降序 |
| `limit` | query | `50` | 最大返回数（1~200） |

成功 `data`：
```json
[
  {
    "code": "BK0477", "name": "白酒",
    "price": null, "change": 1.2, "change_pct": 0.56,
    "total_market_cap": null, "turnover_rate": 1.5,
    "up_count": 10, "down_count": 3,
    "leading_stock": "贵州茅台", "leading_stock_change_pct": 2.1
  }
]
```

### 4.4 板块详情

```
GET /api/v1/sector/{name}
```

| 参数 | 位置 | 说明 |
|------|------|------|
| `name` | path | 板块名称（如 `白酒`、`小金属`） |

成功 `data`：
```json
{
  "quote": { ... },   // 同 4.3 单条 SectorQuote
  "constituents": [
    { "code": "600519", "name": "贵州茅台" },
    { "code": "000858", "name": "五粮液" }
  ]
}
```

### 4.5 大盘指数

```
GET /api/v1/market/index          # 主要指数（白名单 8 个）
GET /api/v1/market/index/all      # 全部指数（按分组）
```

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `group` | query | `沪深重要指数` | 仅 `/all` 使用：沪深重要/上证系列/深证系列/指数成份/中证系列 |

主要指数白名单：上证指数、深证成指、创业板指、科创50、北证50、沪深300、中证500、中证1000

成功 `data`：
```json
[
  {
    "code": "000001", "name": "上证指数",
    "price": 3200.0, "change_pct": 0.56, "change": 17.8,
    "volume": null, "amount": null, "amplitude": 0.8,
    "high": 3210.0, "low": 3180.0, "open": 3190.0, "prev_close": 3182.2
  }
]
```

### 4.6 搜索

```
GET /api/v1/search?q={keyword}&limit={limit}
```

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `q` | query | 必填 | 关键词（代码 / 简称 / 拼音首字母），min_length=1 |
| `limit` | query | 20 | 最大返回数（1~100） |

成功 `data`（按相关度降序）：
```json
[
  { "code": "600519", "name": "贵州茅台", "market": "上证", "type": "stock", "score": 100 }
]
```

搜索维度：精确代码（100）→ 简称包含（80）→ 拼音全拼（60/50）→ 拼音首字母（40/30）

> 索引由定时任务每日 09:20 构建。索引为空时返回 `[]`，可调用 `POST /admin/sync` 手动触发。

### 4.7 健康检查

```
GET /health          存活探针（进程在跑即 ok）
GET /health/ready    就绪探针（检查缓存 / DB 依赖）
```

### 4.8 运维端点

```
POST /admin/sync       手动触发：股票 → ETF → 行业映射 → 重建索引
POST /admin/reindex    仅从 DB 重建搜索索引
```

---

## 5. 前端联调建议

### 5.1 开发流程

1. `GET /health/ready` 确认后端依赖正常
2. `POST /admin/sync` 首次同步（DB 就绪后），让搜索可用
3. `GET /api/v1/search?q=600519` 验证搜索
4. `GET /api/v1/stock/list?page=1&page_size=5` 验证行情

### 5.2 axios 封装示例

```js
import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:8000', timeout: 10000 })

// 统一响应拦截：解包 data
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

// 使用（已解包，无需 .data.data）
const detail = await api.get('/api/v1/stock/600519')
```

### 5.3 注意事项

- **个股端点仅支持 A 股**：代码正则 `^[0368]\d{4,5}$`
- **搜索为空不报错**：索引未构建时返回 `{code:0, data:[]}`
- **实时行情有缓存**：列表 120s / 个股 30s TTL
- **数据源不稳定**：后端有多源 fallback（东方财富→新浪→腾讯），但仍可能返回 50201，建议前端重试 1~2 次
- **限流**：未来 AI 端点会有 429，需读 `Retry-After` 头做倒计时

---

## 6. API 覆盖范围

| 能力 | 状态 | 端点 |
|------|------|------|
| 股票/ETF 行情列表 | ✅ | `GET /api/v1/stock/list` |
| A 股个股详情 | ✅ | `GET /api/v1/stock/{code}` |
| 板块涨跌排行 | ✅ | `GET /api/v1/sector/list` |
| 板块详情（成分股） | ✅ | `GET /api/v1/sector/{name}` |
| 大盘指数 | ✅ | `GET /api/v1/market/index` |
| 搜索（代码/简称/拼音） | ✅ | `GET /api/v1/search` |
| 健康检查 | ✅ | `GET /health`、`GET /health/ready` |
| 运维同步 | ✅ | `POST /admin/sync`、`POST /admin/reindex` |
| ETF 详情 | ⏳ 待实现 | — |
| 主力资金独立端点 | ⏳ 待实现 | — |
| K 线 | ⏳ 待实现 | — |
| AI 分析 | ⏳ 待实现 | — |
