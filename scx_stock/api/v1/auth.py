"""
@description 认证 API：请求授权码（发邮件）+ 验证授权码 + 退出。

授权码为 16 位随机字符串，有效期默认 3 天（通过 SCX_AUTH_CODE_TTL_HOURS 配置），发送到固定邮箱。
"""

import logging
import secrets

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from pydantic import BaseModel, Field

from scx_stock.config.dynamic import get_dynamic_setting
from scx_stock.config.settings import get_settings
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.storage import repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["认证"])

# 固定收件邮箱
_NOTIFY_EMAIL = "dev.rehab498@passinbox.com"


class VerifyRequest(BaseModel):
    """验证授权码请求。"""

    code: str = Field(..., min_length=16, max_length=16, description="16 位授权码")


@router.post("/request-code", response_model=ApiResponse, summary="请求授权码（发送到邮箱）")
async def request_auth_code() -> dict[str, object]:
    """生成 16 位随机授权码，发送到固定邮箱。

    授权码有效期：DB 动态配置（前端设置页）优先，回退 SCX_AUTH_CODE_TTL_HOURS，默认 72 小时（3 天）。

    :returns: 统一响应，data 含 sent 布尔值。
    """
    # 生成 16 位授权码（大写字母 + 数字，避免歧义字符）
    import string

    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(16))

    # 存入 DB（有效期动态读取：前端修改后即时生效，非法值回退默认 72 小时）
    raw_ttl = await get_dynamic_setting("auth_code_ttl_hours")
    try:
        ttl_hours = max(1, int(raw_ttl))
    except (TypeError, ValueError):
        ttl_hours = 72
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    try:
        await repo.create_auth_code(code, expires_at)
    except Exception as e:  # noqa: BLE001
        logger.exception("授权码存库失败: %s", e)
        return ok({"sent": False, "message": f"授权码存库失败: {e}"})

    # 发邮件
    from scx_stock.notify.email_sender import send_email

    s = get_settings()
    recipients = [e.strip() for e in s.notify_emails.split(",") if e.strip()] if s.notify_emails else []
    # 追加固定邮箱
    if _NOTIFY_EMAIL not in recipients:
        recipients.append(_NOTIFY_EMAIL)

    if not recipients:
        logger.warning("未配置收件人，授权码 %s 仅存 DB", code)
        return ok({"sent": False, "message": "未配置收件人，授权码已生成但未发送"})

    # 有效期展示：可整除 24 时按天显示，否则按小时
    ttl_text = f"{ttl_hours // 24} 天" if ttl_hours % 24 == 0 else f"{ttl_hours} 小时"

    html = f"""
    <h2>访问授权码</h2>
    <p>您请求了一个新的访问授权码：</p>
    <p style="font-size: 24px; font-weight: bold; letter-spacing: 4px;
              font-family: monospace; background: #f0f0f0; padding: 12px;
              border-radius: 6px; text-align: center;">{code}</p>
    <p>有效期：{ttl_text}</p>
    <p>请在授权码输入框中填写此码以访问系统。</p>
    """
    try:
        sent, error = await send_email(recipients, html)
        if sent:
            logger.info("授权码已发送到 %s", recipients)
            return ok({"sent": True, "message": f"授权码已发送至 {_NOTIFY_EMAIL}"})
        else:
            logger.warning("授权码邮件发送失败: %s", error)
            return ok({"sent": False, "message": f"邮件发送失败: {error}"})
    except Exception as e:  # noqa: BLE001
        logger.exception("授权码邮件发送异常: %s", e)
        return ok({"sent": False, "message": f"邮件发送失败: {e}"})


@router.post("/verify", response_model=ApiResponse, summary="验证授权码")
async def verify_auth_code(body: VerifyRequest) -> dict[str, object]:
    """验证用户输入的授权码是否有效。

    :param body: 含 code 字段。
    :returns: 统一响应，data 含 valid 布尔值。
    """
    valid = await repo.validate_auth_code(body.code)
    if valid:
        logger.info("授权码验证通过: %s...", body.code[:4])
        return ok({"valid": True})
    else:
        return ok({"valid": False, "message": "授权码无效或已过期"})


@router.post("/logout", response_model=ApiResponse, summary="退出登录（停用授权码）")
async def logout_auth_code(
    body: VerifyRequest | None = None,
) -> dict[str, object]:
    """停用当前授权码。

    :param body: 含 code 字段（可选）。
    :returns: 统一响应。
    """
    if body and body.code:
        await repo.deactivate_auth_code(body.code)
        logger.info("授权码已停用: %s...", body.code[:4])
    return ok({"done": True})
