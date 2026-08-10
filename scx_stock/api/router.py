"""
@description API 路由聚合，统一挂载 v1 子路由。
"""

from fastapi import APIRouter

from scx_stock.api.v1 import analysis, gold, market, search, sector, settings, stock, watchlist

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(stock.router)
api_router.include_router(search.router)
api_router.include_router(sector.router)
api_router.include_router(market.router)
api_router.include_router(gold.router)
api_router.include_router(analysis.router)
api_router.include_router(watchlist.router)
api_router.include_router(settings.router)
