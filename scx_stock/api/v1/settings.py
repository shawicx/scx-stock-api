"""
@description 应用配置 API：读取/更新 LLM 与 SMTP 配置，测试 LLM 连接。

配置存 DB app_setting 表，前端修改后即时生效（无需重启）。
API Key 在 GET 时脱敏显示。
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from scx_stock.config.dynamic import _SETTING_KEYS, get_dynamic_settings
from scx_stock.middleware.rate_limit import ai_rate_limit
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.storage import repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["应用配置"])

# GET 时需要脱敏的敏感配置键
_SENSITIVE_KEYS = {"llm_api_key", "smtp_password"}


def _mask(value: str | None) -> str | None:
    """脱敏处理：只保留前3位和后4位，中间用 *** 替代。

    :param value: 原始值。
    :returns: 脱敏后的值。
    """
    if not value:
        return value
    if len(value) <= 7:
        return "***"
    return f"{value[:3]}***{value[-4:]}"


class SettingsUpdate(BaseModel):
    """批量更新配置请求体。

    只包含需要更新的键，未提供的键不变。
    """

    llm_provider: str | None = Field(None, description="LLM 提供商：deepseek / glm")
    llm_api_key: str | None = Field(None, description="LLM API Key")
    llm_base_url: str | None = Field(None, description="LLM API Base URL")
    llm_model: str | None = Field(None, description="LLM 模型名")
    llm_timeout: str | None = Field(None, description="LLM 超时秒数")
    smtp_host: str | None = None
    smtp_port: str | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_name: str | None = None
    smtp_use_ssl: str | None = None
    notify_emails: str | None = None


@router.get("", response_model=ApiResponse, summary="获取当前应用配置")
async def get_settings_api() -> dict[str, object]:
    """返回所有配置项（敏感字段脱敏）。

    :returns: 统一响应，data 为 {key: value} 字典。
    """
    settings = await get_dynamic_settings()
    # 脱敏
    masked = {
        k: (_mask(v) if k in _SENSITIVE_KEYS and v else v)
        for k, v in settings.items()
    }
    return ok(masked)


@router.put("", response_model=ApiResponse, summary="更新应用配置")
async def update_settings_api(
    body: SettingsUpdate,
) -> dict[str, object]:
    """批量更新配置。空值字段不更新。

    :param body: 配置更新请求体。
    :returns: 统一响应，data 为更新后的配置数量。
    """
    # 收集非 None 字段
    updates: dict[str, str] = {}
    for key in _SETTING_KEYS:
        val = getattr(body, key, None)
        if val is not None:
            updates[key] = val

    if not updates:
        return ok({"updated": 0})

    count = await repo.upsert_settings(updates)
    logger.info("应用配置更新 %d 项: %s", count, list(updates.keys()))
    return ok({"updated": count})


@router.post("/test-llm", response_model=ApiResponse, summary="测试 LLM 连接")
async def test_llm_connection(
    _=Depends(ai_rate_limit()),
) -> dict[str, object]:
    """测试当前 LLM 配置是否可用（发送一条简单 prompt）。

    :returns: 统一响应，data 含 success / message / reply。
    """
    from scx_stock.llm.client import get_llm_client

    client = get_llm_client()
    if not await client.available():
        return ok(
            {"success": False, "message": "LLM API Key 未配置", "reply": ""}
        )

    try:
        reply = await client.chat(
            system="你是一个测试助手。",
            user="请回复「连接成功」四个字。",
            max_tokens=20,
        )
        return ok(
            {"success": True, "message": "连接成功", "reply": reply}
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 测试连接失败: %s", e)
        return ok(
            {"success": False, "message": f"连接失败: {e}", "reply": ""}
        )
