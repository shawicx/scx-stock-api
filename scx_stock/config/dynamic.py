"""
@description 动态配置读取：优先读 DB app_setting 表，无则回退 .env（Settings）。

供 LLM 客户端、SMTP 邮件等运行时可修改的配置使用。
前端配置页面写入 DB 后，下次读取即生效，无需重启。
"""

import logging
from typing import Any

from scx_stock.config.settings import get_settings

logger = logging.getLogger(__name__)

# DB app_setting 表的 key 与 Settings 属性名的映射
# key 命名规则：去掉 SCX_ 前缀、转小写（如 SCX_LLM_API_KEY → llm_api_key）
_SETTING_KEYS = [
    "llm_provider",
    "llm_api_key",
    "llm_base_url",
    "llm_model",
    "llm_timeout",
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "smtp_from_name",
    "smtp_use_ssl",
    "notify_emails",
]


async def get_dynamic_setting(key: str, default: Any = None) -> str | None:
    """读取单个配置项，优先 DB，回退 .env。

    :param key: 配置键（如 llm_api_key）。
    :param default: DB 和 .env 都无时的默认值。
    :returns: 配置值字符串。
    """
    # 1. 优先查 DB
    try:
        from scx_stock.storage import repo

        all_settings = await repo.get_all_settings()
        if key in all_settings:
            return all_settings[key]
    except Exception as e:  # noqa: BLE001
        logger.debug("get_dynamic_setting DB read failed for %s: %s", key, e)

    # 2. 回退 .env（Settings 属性）
    s = get_settings()
    val = getattr(s, key, None)
    return val if val is not None else default


async def get_dynamic_settings(keys: list[str] | None = None) -> dict[str, str | None]:
    """批量读取配置项。

    :param keys: 配置键列表；None 时读全部已知键。
    :returns: {key: value} 字典。
    """
    target_keys = keys or _SETTING_KEYS
    try:
        from scx_stock.storage import repo

        db_settings = await repo.get_all_settings()
    except Exception as e:  # noqa: BLE001
        logger.debug("get_dynamic_settings DB read failed: %s", e)
        db_settings = {}

    s = get_settings()
    result: dict[str, str | None] = {}
    for key in target_keys:
        if key in db_settings:
            result[key] = db_settings[key]
        else:
            result[key] = getattr(s, key, None)
    return result
