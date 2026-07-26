"""
@description 数据库初始化测试：验证自动建库判断逻辑与维护库 DSN 生成，不依赖真实 PG。
"""

import asyncpg
import pytest

from scx_stock.config.settings import Settings
from scx_stock.storage import db


# ---------- _is_database_missing_error ----------


def test_is_db_missing_matches_invalid_catalog_name():
    """asyncpg InvalidCatalogNameError 判定为库不存在。"""
    exc = asyncpg.exceptions.InvalidCatalogNameError(
        'database "scx-stock" does not exist'
    )
    assert db._is_database_missing_error(exc) is True


def test_is_db_missing_matches_sqlalchemy_wrapped_orig():
    """SQLAlchemy 包装异常时，从 .orig 取原始 asyncpg 异常判定。"""

    class FakeOperationalError(Exception):
        def __init__(self, orig):
            self.orig = orig

    wrapped = FakeOperationalError(
        asyncpg.exceptions.InvalidCatalogNameError("no such db")
    )
    assert db._is_database_missing_error(wrapped) is True


def test_is_db_missing_matches_message_keyword():
    """无具体异常类型时，用消息关键字兜底匹配。"""
    exc = RuntimeError('FATAL: database "scx-stock" does not exist')
    assert db._is_database_missing_error(exc) is True


def test_is_db_missing_rejects_auth_error():
    """认证失败/密码错误不应判定为库不存在。"""
    exc = asyncpg.exceptions.InvalidPasswordError("bad password")
    assert db._is_database_missing_error(exc) is False


def test_is_db_missing_rejects_connection_error():
    """连接拒绝（PG 未启动）不应判定为库不存在。"""
    exc = ConnectionError("connection refused")
    assert db._is_database_missing_error(exc) is False


# ---------- _maintenance_dsn ----------


def test_maintenance_dsn_points_to_postgres_db(monkeypatch):
    """维护 DSN 指向 postgres 维护库，复用应用账号与端口。"""
    monkeypatch.setattr(
        db,
        "get_settings",
        lambda: Settings(
            db_host="127.0.0.1",
            db_port=5433,
            db_user="scx",
            db_password="secret",
            db_name="scx-stock",
        ),
    )
    dsn = db._maintenance_dsn()
    assert dsn == "postgresql+asyncpg://scx:secret@127.0.0.1:5433/postgres"


# ---------- db_auto_create 开关 ----------


def test_db_auto_create_default_true():
    """db_auto_create 默认开启，便于开发环境。"""
    s = Settings()
    assert s.db_auto_create is True
