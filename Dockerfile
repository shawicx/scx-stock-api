# ============================================================
# scx-stock-api Dockerfile（多阶段构建）
# 阶段 1：用 uv 安装依赖到 .venv
# 阶段 2：精简运行时镜像，仅含 .venv + 源码
# ============================================================

# ---------- 阶段 1：构建 ----------
FROM python:3.13-slim AS builder

# 安装 uv（从官方镜像复制二进制，无需 pip）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 先复制依赖清单，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./

# 安装依赖到 .venv（不安装项目本身）
RUN uv sync --frozen --no-install-project

# 复制源码
COPY scx_stock/ scx_stock/

# 安装项目本身
RUN uv sync --frozen

# ---------- 阶段 2：运行时 ----------
FROM python:3.13-slim

# 从 builder 复制虚拟环境和源码
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/scx_stock /app/scx_stock
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

WORKDIR /app

# 激活虚拟环境
ENV PATH="/app/.venv/bin:$PATH"

# 生产环境默认配置（可被 --env-file 覆盖）
ENV SCX_APP_ENV=prod
ENV SCX_APP_HOST=0.0.0.0
ENV SCX_APP_PORT=3800

EXPOSE 3800

CMD ["uvicorn", "scx_stock.main:app", "--host", "0.0.0.0", "--port", "3800"]
