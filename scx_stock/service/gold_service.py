"""
@description 黄金行情业务编排层。
"""

import logging

from scx_stock.cache.backend import CacheBackend
from scx_stock.repository.gold_repo import GoldRepository
from scx_stock.schema.gold import GoldQuote

logger = logging.getLogger(__name__)


class GoldService:
    """黄金行情 Service。

    :param repo: 黄金 Repository。
    :param cache: 缓存后端。
    """

    def __init__(self, repo: GoldRepository, cache: CacheBackend) -> None:
        self._repo = repo
        self._cache = cache

    async def list_gold_quotes(self) -> list[GoldQuote]:
        """获取黄金品种实时行情列表。

        :returns: GoldQuote 列表。
        """
        return await self._repo.list_gold_quotes()
