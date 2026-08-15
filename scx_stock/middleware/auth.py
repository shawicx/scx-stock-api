"""
@description 授权码校验依赖，通过 X-Access-Token 头或 Authorization: Bearer 携带。

挂载到 api_router 和 admin 端点（/health 放行）。
支持两种认证方式：
  1. 动态授权码（16 位，通过 /auth/request-code 获取，有效期默认 3 天可配置，存 DB）
  2. 固定测试 token（通过 SCX_TEST_TOKEN 环境变量配置，用于测试/开发环境）
"""

import logging

from fastapi import Header, HTTPException

from scx_stock.config.settings import get_settings
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

    校验优先级：
      1. 固定测试 token（SCX_TEST_TOKEN 配置时，匹配即放行）
      2. 动态授权码（DB auth_code 表校验）

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

    # 1. 固定测试 token 校验（测试/开发环境）
    test_token = get_settings().test_token
    if test_token and token == test_token:
        return

    # 2. 动态授权码校验（DB auth_code 表）
    valid = await repo.validate_auth_code(token)
    if not valid:
        logger.info("授权码校验失败: %s...", token[:4])
        raise HTTPException(status_code=401, detail="授权码无效或已过期")
