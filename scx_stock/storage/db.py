"""
@description 数据库引擎与会话管理，基于 SQLAlchemy 异步引擎。
"""

import logging
from collections.abc import AsyncGenerator

import asyncpg
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from scx_stock.config.settings import get_dsn, get_settings

logger = logging.getLogger(__name__)


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


def _is_database_missing_error(exc: Exception) -> bool:
    """判断异常是否为「目标数据库不存在」。

    asyncpg 把 ``FATAL: database "xxx" does not exist`` 抛为
    InvalidCatalogNameError；SQLAlchemy 包装在 OperationalError.orig 中。
    另外用消息关键字兜底，兼容不同 PG 客户端/版本。

    :param exc: 捕获的异常。
    :returns: 是否为库不存在错误。
    """
    if isinstance(exc, asyncpg.exceptions.InvalidCatalogNameError):
        return True
    orig = getattr(exc, "orig", None)
    if isinstance(orig, asyncpg.exceptions.InvalidCatalogNameError):
        return True
    msg = str(exc).lower()
    return "does not exist" in msg and "database" in msg


def _maintenance_dsn() -> str:
    """生成连接到 postgres 维护库的 DSN（用于 CREATE DATABASE）。

    :returns: 指向 postgres 库的 asyncpg 连接串。
    """
    s = get_settings()
    return (
        f"postgresql+asyncpg://{s.db_user}:{s.db_password}"
        f"@{s.db_host}:{s.db_port}/postgres"
    )


async def _create_database_if_missing() -> bool:
    """连接 postgres 维护库，创建目标数据库（若不存在）。

    :returns: 是否实际创建了数据库（已存在返回 False）。
    :raises: 创建过程中的原始异常（如权限不足）。
    """
    s = get_settings()
    # CREATE DATABASE 不能在事务里执行，用裸连接走 autocommit
    conn = await asyncpg.connect(
        host=s.db_host,
        port=s.db_port,
        user=s.db_user,
        password=s.db_password,
        database="postgres",
    )
    try:
        # 参数化方式不支持 DDL，db_name 来自受信配置，直接拼入
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", s.db_name
        )
        if exists:
            return False
        await conn.execute(f'CREATE DATABASE "{s.db_name}"')
        logger.info("auto-created database: %s", s.db_name)
        return True
    finally:
        await conn.close()


def _align_varchar_lengths_sync(conn) -> list[str]:
    """对比 ORM 模型与库中 varchar 列长度，扩容偏短的列。

    ``create_all`` 只建新表不改旧表，模型扩长（如 stock.pinyin 64→128）后
    旧库不会自动跟进，超长值写入会报 StringDataRightTruncationError。
    此函数按 information_schema 实测长度决定是否 ALTER（表/列名来自
    受信的 ORM 元数据，无注入风险）。

    :param conn: SQLAlchemy 同步连接（由 run_sync 提供）。
    :returns: 变更描述列表（如 "stock.pinyin: 64 -> 128"）。
    """
    from sqlalchemy import text

    changed: list[str] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            model_len = getattr(column.type, "length", None)
            if model_len is None:
                continue
            row = conn.execute(
                text(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table.name, "c": column.name},
            ).fetchone()
            if row is None or row[0] is None or row[0] >= model_len:
                continue
            conn.execute(
                text(
                    f'ALTER TABLE {table.name} ALTER COLUMN "{column.name}" '
                    f"TYPE VARCHAR({model_len})"
                )
            )
            changed.append(f"{table.name}.{column.name}: {row[0]} -> {model_len}")
    return changed


async def init_db() -> None:
    """初始化数据库：建表并自动扩容偏短的 varchar 列（开发期使用，生产用 Alembic 迁移）。

    若 ``db_auto_create`` 开启且目标库不存在，自动连 postgres 维护库创建。
    建表后对比模型与库中 varchar 长度，ALTER 扩容偏短的列（旧库 schema 漂移自愈）。
    """
    from scx_stock.storage import models  # noqa: F401 确保模型已注册

    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        if not (
            get_settings().db_auto_create and _is_database_missing_error(exc)
        ):
            raise
        logger.warning("database missing, attempting auto-create: %s", exc)
        await _create_database_if_missing()
        # 创建后重建引擎（原引擎缓存了失效连接），再建表
        await close_db()
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # varchar 列长度对齐（create_all 不改旧表，扩容漂移列）
    async with engine.begin() as conn:
        changed = await conn.run_sync(_align_varchar_lengths_sync)
    if changed:
        logger.info("aligned varchar columns: %s", ", ".join(changed))


async def close_db() -> None:
    """关闭数据库引擎。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
