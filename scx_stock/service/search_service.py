"""
@description 搜索业务编排，先查缓存命中则返回，否则查内存索引。
"""

import logging

from scx_stock.cache import keys
from scx_stock.cache.backend import CacheBackend
from scx_stock.search.index import get_index

logger = logging.getLogger(__name__)

_TTL_SEARCH = 300  # 搜索结果缓存 5 分钟


class SearchService:
    """搜索 Service。

    :param cache: 缓存后端。
    """

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    async def search(self, keyword: str, limit: int = 20) -> list[dict[str, object]]:
        """按关键词搜索。

        :param keyword: 关键词。
        :param limit: 最大返回数。
        :returns: 结果列表。
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return []

        cache_key = keys.search_result(keyword)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        results = get_index().search(keyword, limit=limit)
        await self._cache.set(cache_key, results, _TTL_SEARCH)
        return results

    async def index_size(self) -> int:
        """返回当前索引条目数。

        :returns: 条目数。
        """
        return get_index().size()
