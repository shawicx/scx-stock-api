"""
@description 全局配置，基于环境变量加载。包含应用、数据库、缓存、限流等配置项。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """定位项目根目录（包含 pyproject.toml 的目录）。

    避免依赖进程 cwd 解析 .env，保证从任意目录启动都能读到同一份配置。

    :returns: 项目根目录 Path。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # 兜底：退回到包的上两级（config -> scx_stock -> 根）
    return here.parents[2]


# .env 固定指向项目根目录，不随进程 cwd 变化
_ENV_FILE = _project_root() / ".env"


class Settings(BaseSettings):
    """应用全局配置。"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
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
    db_user: str = "scx"
    db_password: str = "your_secure_password_here"
    db_name: str = "scx-stock"
    db_echo: bool = False
    # 服务启动时若目标库不存在是否自动创建（开发期便利；生产建议关闭）
    db_auto_create: bool = True

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
