"""
@description 授权码校验依赖，通过 X-Access-Token 头或 Authorization: Bearer 携带。

挂载到 api_router 和 admin 端点（/health 放行）。
DB 中无 auth_code 表数据时（首次使用/DB 不可用），跳过校验保持兼容。
"""

import logging

from fastapi import Header, HTTPException

from scx_stock.storage import repo

logger = logging.getLogger(__name__)


async def require_access_token(
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
    authorization: str | None = Header(None),
) -> None:
    """校验请求携带的授权码是否有效。

    支持两种头：
      - ``X-Access-Token: <code>``
      - ``Authorization: Bearer <code>``

    :param x_access_token: X-Access-Token 头值。
    :param authorization: Authorization 头值。
    :raises HTTPException: 授权码无效时返回 401。
    """
    # 提取 token
    token = x_access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]

    if not token:
        raise HTTPException(status_code=401, detail="缺少授权码")

    valid = await repo.validate_auth_code(token)
    if not valid:
        logger.info("授权码校验失败: %s...", token[:4])
        raise HTTPException(status_code=401, detail="授权码无效或已过期")
