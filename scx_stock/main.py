"""
@description FastAPI 应用入口，装配路由、CORS、异常处理、健康检查、生命周期。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scx_stock.api.errors import register_exception_handlers
from scx_stock.api.router import api_router
from scx_stock.cache.backend import get_cache
from scx_stock.config.settings import get_settings
from scx_stock.scheduler.runner import get_scheduler
from scx_stock.scheduler.sync_jobs import rebuild_search_index, sync_all
from scx_stock.schema.common import ok
from scx_stock.storage.db import close_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

__version__ = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 启动调度器，关闭时释放资源。

    :param app: FastAPI 应用。
    """
    s = get_settings()
    logger.info("starting %s (env=%s)", s.app_name, s.app_env)
    try:
        await init_db()
        logger.info("database initialized")
    except Exception as e:  # noqa: BLE001
        # DB 不可用不应阻断启动，便于无 DB 环境下调试 Provider/缓存路径
        logger.warning("init_db skipped: %s", e)

    scheduler = get_scheduler()
    scheduler.start()

    yield

    scheduler.shutdown()
    await close_db()
    logger.info("shutdown complete")


def _register_cors(app: FastAPI) -> None:
    """注册 CORS 中间件，允许源来自配置。

    :param app: FastAPI 应用。
    """
    s = get_settings()
    origins = s.cors_origin_list()
    allow_all = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=not allow_all,  # 通配源下不能携带凭证
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS configured: %s", "*" if allow_all else origins)


def _register_health(app: FastAPI) -> None:
    """注册健康检查端点。

    - ``GET /health``        存活探针，始终返回 200
    - ``GET /health/ready``  就绪探针，检查缓存/DB 等依赖

    :param app: FastAPI 应用。
    """

    @app.get("/health", tags=["健康检查"], summary="存活探针")
    async def liveness() -> dict[str, object]:
        """存活探针：只要进程在跑就返回 ok。

        :returns: 统一响应，data 含 status=ok。
        """
        return ok({"status": "ok", "version": __version__})

    @app.get("/health/ready", tags=["健康检查"], summary="就绪探针")
    async def readiness() -> dict[str, object]:
        """就绪探针：检查缓存与 DB 是否可用。

        :returns: 统一响应，data 含各组件状态与总体 status。
        """
        checks: dict[str, str] = {}

        # 缓存
        try:
            await get_cache()
            checks["cache"] = "ok"
        except Exception as e:  # noqa: BLE001
            checks["cache"] = f"fail: {e}"

        # DB（仅探测，失败不抛）
        try:
            from scx_stock.storage import repo

            count = await repo.count_stocks()
            checks["db"] = f"ok ({count} rows)"
        except Exception as e:  # noqa: BLE001
            checks["db"] = f"fail: {e}"

        overall = "ok" if all(v == "ok" or v.startswith("ok") for v in checks.values()) else "degraded"
        return ok({"status": overall, "checks": checks})


def _register_admin(app: FastAPI) -> None:
    """注册运维端点：手动触发同步 / 重建索引。

    :param app: FastAPI 应用。
    """

    @app.post("/admin/sync", tags=["运维"], summary="手动触发全量同步")
    async def _manual_sync() -> dict[str, object]:
        """手动触发：股票列表 → ETF 列表 → 重建索引。

        :returns: 统一响应，data 为同步计数；失败时 code 非 0。
        """
        try:
            result = await sync_all()
            return ok(result)
        except Exception as e:  # noqa: BLE001
            logger.exception("manual sync failed")
            return {"code": 1, "message": f"sync failed: {e}", "data": None}

    @app.post("/admin/reindex", tags=["运维"], summary="仅重建搜索索引")
    async def _manual_reindex() -> dict[str, object]:
        """从 DB 重建内存搜索索引（不拉取数据源）。

        :returns: 统一响应，data 为索引大小；DB 不可用时 code 非 0。
        """
        try:
            result = await rebuild_search_index()
            return ok(result)
        except Exception as e:  # noqa: BLE001
            logger.exception("manual reindex failed")
            return {"code": 1, "message": f"reindex failed: {e}", "data": None}


def create_app() -> FastAPI:
    """构建 FastAPI 应用实例。

    :returns: FastAPI 应用。
    """
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version=__version__,
        description="股票行情与 AI 分析后端 API",
        lifespan=lifespan,
    )
    _register_cors(app)
    register_exception_handlers(app)
    _register_health(app)
    _register_admin(app)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "scx_stock.main:app",
        host=s.app_host,
        port=s.app_port,
        reload=s.app_env == "dev",
    )
