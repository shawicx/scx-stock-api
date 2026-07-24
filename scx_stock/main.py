"""
@description FastAPI 应用入口，装配路由、异常处理、生命周期。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from scx_stock.api.errors import register_exception_handlers
from scx_stock.api.router import api_router
from scx_stock.config.settings import get_settings
from scx_stock.storage.db import close_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表，关闭时释放资源。

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

    yield

    await close_db()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    """构建 FastAPI 应用实例。

    :returns: FastAPI 应用。
    """
    s = get_settings()
    app = FastAPI(title=s.app_name, lifespan=lifespan)
    app.include_router(api_router)
    register_exception_handlers(app)
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
