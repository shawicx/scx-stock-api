"""
@description 指数（大盘）业务编排层。
"""

import logging

from scx_stock.cache.backend import CacheBackend
from scx_stock.repository.index_repo import IndexRepository
from scx_stock.schema.index import IndexQuote

logger = logging.getLogger(__name__)


class IndexService:
    """指数业务 Service。

    :param repo: IndexRepository 实例。
    :param cache: 缓存后端。
    """

    def __init__(self, repo: IndexRepository, cache: CacheBackend) -> None:
        self._repo = repo
        self._cache = cache

    async def list_major_indexes(self) -> list[IndexQuote]:
        """获取主要大盘指数（上证/深证/创业板等白名单）。

        :returns: IndexQuote 列表。
        """
        return await self._repo.list_major_indexes()

    async def list_indexes(self, group: str = "沪深重要指数") -> list[IndexQuote]:
        """获取指定分组的全部指数。

        :param group: 指数分组。
        :returns: IndexQuote 列表。
        """
        return await self._repo.list_indexes(group)
