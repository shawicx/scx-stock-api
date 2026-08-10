"""
@description 黄金 Repository：缓存 + Provider 编排。
"""

import logging

from scx_stock.cache import keys
from scx_stock.cache.backend import CacheBackend
from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.schema.gold import GoldQuote

logger = logging.getLogger(__name__)

# 黄金行情分钟级，TTL 2 分钟
_TTL_GOLD = 120


class GoldRepository:
    """黄金领域 Repository。

    :param cache: 缓存后端。
    """

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    async def list_gold_quotes(self) -> list[GoldQuote]:
        """获取黄金品种实时行情列表（带缓存）。

        :returns: GoldQuote 列表。
        """
        cache_key = keys.gold_quotes()
        cached = await self._cache.get(cache_key)
        if cached:
            return [GoldQuote(**item) for item in cached]

        provider = AkshareProvider()
        quotes = await provider.list_gold_quotes()
        await self._cache.set(
            cache_key, [q.model_dump() for q in quotes], _TTL_GOLD
        )
        return quotes
