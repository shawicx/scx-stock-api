"""
@description API 层依赖注入，集中提供 Service / Repository / Cache 实例。
"""

from typing import AsyncGenerator

from fastapi import Depends

from scx_stock.cache.backend import CacheBackend, get_cache
from scx_stock.repository.gold_repo import GoldRepository
from scx_stock.repository.index_repo import IndexRepository
from scx_stock.repository.router import StockRepository
from scx_stock.repository.sector_repo import SectorRepository
from scx_stock.service.gold_service import GoldService
from scx_stock.service.index_service import IndexService
from scx_stock.service.search_service import SearchService
from scx_stock.service.sector_service import SectorService
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


async def get_sector_service(
    cache: CacheBackend = Depends(get_cache_dep),
) -> SectorService:
    """提供 SectorService。

    :param cache: 缓存后端（依赖注入）。
    :returns: SectorService 实例。
    """
    repo = SectorRepository(cache)
    return SectorService(repo, cache)


async def get_index_service(
    cache: CacheBackend = Depends(get_cache_dep),
) -> IndexService:
    """提供 IndexService。

    :param cache: 缓存后端（依赖注入）。
    :returns: IndexService 实例。
    """
    repo = IndexRepository(cache)
    return IndexService(repo, cache)


async def get_gold_service(
    cache: CacheBackend = Depends(get_cache_dep),
) -> GoldService:
    """提供 GoldService。

    :param cache: 缓存后端（依赖注入）。
    :returns: GoldService 实例。
    """
    repo = GoldRepository(cache)
    return GoldService(repo, cache)
