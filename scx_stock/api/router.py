"""
@description API 路由聚合，统一挂载 v1 子路由。
"""

from fastapi import APIRouter

from scx_stock.api.v1 import search, stock

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(stock.router)
api_router.include_router(search.router)
