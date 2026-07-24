"""
@description 数据库引擎与会话管理，基于 SQLAlchemy 异步引擎。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from scx_stock.config.settings import get_dsn


class Base(DeclarativeBase):
    """ORM 基类。"""


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """获取全局异步引擎单例。

    :returns: AsyncEngine 实例。
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_dsn(), echo=__is_echo())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取会话工厂单例。

    :returns: async_sessionmaker 实例。
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供数据库会话。

    :returns: AsyncSession。
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


def __is_echo() -> bool:
    from scx_stock.config.settings import get_settings

    return get_settings().db_echo


async def init_db() -> None:
    """初始化数据库：建表（开发期使用，生产用 Alembic 迁移）。"""
    from scx_stock.storage import models  # noqa: F401 确保模型已注册

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """关闭数据库引擎。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
