"""
@description API 路由聚合，统一挂载 v1 子路由。

认证依赖（require_access_token）挂在 api_router 上，
但 auth 路由（request-code / verify / logout）需要在认证之前放行。
"""

from fastapi import APIRouter, Depends

from scx_stock.api.v1 import analysis, auth, gold, market, search, sector, settings, stock, watchlist
from scx_stock.middleware.auth import require_access_token

# auth 路由不需要认证，单独挂在无认证的路由上
public_router = APIRouter(prefix="/api/v1")
public_router.include_router(auth.router)

# 其余路由需要认证
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_access_token)])
api_router.include_router(stock.router)
api_router.include_router(search.router)
api_router.include_router(sector.router)
api_router.include_router(market.router)
api_router.include_router(gold.router)
api_router.include_router(analysis.router)
api_router.include_router(watchlist.router)
api_router.include_router(settings.router)
