# 部署指南

> 部署到阿里云 ECS（与 scx-backend 共用同一台 ECS）。

---

## 1. 部署架构

```text
用户 → :6900 (nginx) ──静态文件──→ scx-gold 前端 SPA
                     └─/api,/health,/admin──→ :3800 (scx-stock-api)
                                                      ├─ PG :5434 (scx-stock-postgres)
                                                      └─ Redis :6389 (scx-stock-redis)
```

| 服务 | 端口 | 说明 |
|------|:----:|------|
| nginx（前端） | 6900 | 对外入口，托管 SPA + 反代 API |
| scx-stock-api（后端） | 3800 | FastAPI + Uvicorn |
| PostgreSQL | 5434 | 独立容器（与 scx-backend 的 5433 隔离） |
| Redis | 6389 | 独立容器（与 scx-backend 的 6388 隔离） |

---

## 2. CI/CD 流程

`.github/workflows/deploy.yml`（工作流名 `CI/CD`）：

```text
push main / workflow_dispatch:
  Job 1: test          → pytest（PR 也执行）
  Job 2: build-and-push → docker build → tag(latest+sha) → push 阿里云 ACR
  Job 3: deploy        → SSH 登录 ECS → 拉镜像 → 启动容器 → 健康检查

pull_request:
  Job 1: test          → 仅测试，不部署
```

### 部署脚本逻辑（SSH 内联）

1. 校验 ECS 上的 `.env` 文件存在
2. 幂等启动 PostgreSQL + Redis 容器（已存在则 start，不存在则创建）
3. 等待 PG 就绪（`pg_isready`，最长 60s）
4. 停止旧容器 → 启动新容器（`--network host --restart=always --env-file`）
5. 健康检查（轮询 `/health`，最长 60s）
6. 失败时打印容器状态、内存、OOM 日志、应用日志

---

## 3. GitHub Secrets

两个仓库（scx-stock-api / scx-gold）共用以下 Secrets：

| Secret | 用途 |
|--------|------|
| `ACR_REGISTRY` | 阿里云容器镜像服务地址（如 `registry.cn-shenzhen.aliyuncs.com`） |
| `ACR_NAMESPACE` | ACR 命名空间 |
| `ACR_USERNAME` | ACR 用户名 |
| `ACR_PASSWORD` | ACR 密码 |
| `ECS_HOST` | ECS 公网 IP |
| `ECS_USER` | SSH 用户（如 root） |
| `ECS_SSH_KEY` | SSH 私钥 |
| `STOCK_ECS_ENV_FILE` | **仅后端**：ECS 上生产 .env 路径（如 `/opt/scx-stock-api/.env`） |

---

## 4. ECS 一次性准备

### 4.1 创建生产 .env

```bash
# SSH 登录 ECS 后
sudo mkdir -p /opt/scx-stock-api
sudo tee /opt/scx-stock-api/.env > /dev/null << 'EOF'
SCX_APP_ENV=prod
SCX_APP_PORT=3800
SCX_DB_HOST=127.0.0.1
SCX_DB_PORT=5434
SCX_DB_USER=scx
SCX_DB_PASSWORD=<你的强密码>
SCX_DB_NAME=scx-stock
SCX_DB_AUTO_CREATE=true
SCX_REDIS_HOST=127.0.0.1
SCX_REDIS_PORT=6389
SCX_CORS_ORIGINS=http://<ECS公网IP>:6900
EOF
```

> **重要**：`.env` 文件不支持行内注释（`# 独立PG` 会破坏 pydantic 解析）。注释单独成行或删除。

### 4.2 在 GitHub 添加 Secret

`STOCK_ECS_ENV_FILE` = `/opt/scx-stock-api/.env`

---

## 5. Docker 构建

### 5.1 后端 Dockerfile（多阶段）

```text
阶段 1 (builder)：python:3.13-slim + uv 安装依赖到 .venv
阶段 2 (runtime)：python:3.13-slim + .venv + 源码
CMD: uvicorn scx_stock.main:app --host 0.0.0.0 --port 3800
```

### 5.2 前端 Dockerfile（多阶段）

```text
阶段 1 (builder)：node:22-alpine + pnpm build → dist/
阶段 2 (runtime)：nginx:alpine + dist/ + nginx.conf
EXPOSE 6900
```

### 5.3 nginx 反向代理（`scx-gold/nginx.conf`）

- `/` → 静态文件（SPA history fallback）
- `/api/` → `http://127.0.0.1:3800`（host 网络）
- `/health` → `http://127.0.0.1:3800`
- `/admin/` → `http://127.0.0.1:3800`

---

## 6. 手动部署（应急）

```bash
# 1. 本地构建并推送
docker build -t scx-stock-api:latest .
docker tag scx-stock-api:latest <ACR>/<NS>/scx-stock-api:latest
docker push <ACR>/<NS>/scx-stock-api:latest

# 2. SSH 登录 ECS
ssh root@<ECS_IP>

# 3. 拉取并重启
docker pull <ACR>/<NS>/scx-stock-api:latest
docker stop scx-stock-api && docker rm scx-stock-api
docker run -d --name scx-stock-api --network host --restart=always \
  --env-file /opt/scx-stock-api/.env <ACR>/<NS>/scx-stock-api:latest

# 4. 健康检查
curl http://localhost:3800/health
```

---

## 7. ECS 上的数据源可用性

**重要**：阿里云 ECS 的 IP 段被东方财富反爬封锁（`push2.eastmoney.com` 返回 `RemoteDisconnected`）。

后端已内置多源 fallback：
- 东方财富（被封）→ 自动切换新浪 `vip.stock.finance.sina.com.cn`（可用）
- 新浪偶发限流 → 自动切换腾讯 `proxy.finance.qq.com`（可用）

无需额外配置，fallback 自动触发。

---

## 8. 资源占用估算

| 容器 | 内存限制 | 说明 |
|------|:--------:|------|
| scx-stock-api | 512m | Python + FastAPI |
| scx-stock-postgres | — | PostgreSQL 16 |
| scx-stock-redis | — | Redis 7 |
| scx-gold (nginx) | 128m | 静态文件托管 |

ECS 总内存约 4G 时可与其他项目（scx-backend）共存。
