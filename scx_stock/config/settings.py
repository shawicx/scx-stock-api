"""
@description 全局配置，基于环境变量加载。包含应用、数据库、缓存、限流等配置项。
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCX_",
        extra="ignore",
    )

    # 应用
    app_name: str = "scx-stock-api"
    app_env: Literal["dev", "prod"] = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # 数据库（PostgreSQL）
    db_host: str = "127.0.0.1"
    db_port: int = 5433
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "scx-stock"
    db_echo: bool = False

    # 缓存（Redis）
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # 数据源
    default_provider: str = "akshare"
    request_timeout: int = 10

    # CORS（前端联调用；逗号分隔的源列表，'*' 表示全部允许）
    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:8080,"
        "http://127.0.0.1:8080"
    )

    # 分页默认值
    default_page_size: int = 20
    max_page_size: int = 100

    # 限流
    ai_rate_limit_per_minute: int = 20

    def cors_origin_list(self) -> list[str]:
        """解析 CORS 允许源为列表。

        :returns: 去空白后的源列表；含 '*' 时返回 ['*']。
        """
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例。

    :returns: Settings 实例。
    """
    return Settings()


def get_dsn() -> str:
    """生成 PostgreSQL 异步 DSN。

    :returns: postgresql+asyncpg 连接串。
    """
    s = get_settings()
    return (
        f"postgresql+asyncpg://{s.db_user}:{s.db_password}"
        f"@{s.db_host}:{s.db_port}/{s.db_name}"
    )
