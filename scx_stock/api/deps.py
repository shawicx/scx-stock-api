"""
@description API 层依赖注入，集中提供 Service / Repository / Cache 实例。
"""

from typing import AsyncGenerator

from fastapi import Depends

from scx_stock.cache.backend import CacheBackend, get_cache
from scx_stock.repository.router import StockRepository
from scx_stock.service.search_service import SearchService
from scx_stock.service.stock_service import StockService


async def get_cache_dep() -> AsyncGenerator[CacheBackend, None]:
    """提供缓存后端。

    :returns: CacheBackend。
    """
    yield await get_cache()


async def get_stock_service(
    cache: CacheBackend = Depends(get_cache_dep),
) -> StockService:
    """提供 StockService。

    :param cache: 缓存后端（依赖注入）。
    :returns: StockService 实例。
    """
    repo = StockRepository(cache)
    return StockService(repo, cache)


async def get_search_service(
    cache: CacheBackend = Depends(get_cache_dep),
) -> SearchService:
    """提供 SearchService。

    :param cache: 缓存后端（依赖注入）。
    :returns: SearchService 实例。
    """
    return SearchService(cache)
