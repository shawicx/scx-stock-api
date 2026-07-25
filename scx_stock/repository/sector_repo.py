"""
@description 板块 Repository：选源 / 降级 / 缓存编排。
"""

import logging

from scx_stock.cache import keys
from scx_stock.cache.backend import CacheBackend
from scx_stock.config.datasource import select_providers
from scx_stock.exceptions.provider import ProviderError
from scx_stock.exceptions.service import NotFoundError
from scx_stock.repository.router import _get_provider
from scx_stock.schema.sector import SectorDetail, SectorQuote

logger = logging.getLogger(__name__)

# 板块列表分钟级，TTL 1~5 分钟
_TTL_SECTOR_LIST = 120
_TTL_SECTOR_DETAIL = 120


class SectorRepository:
    """板块领域 Repository。

    板块/指数不依赖市场识别（板块按名称、指数按分组），选源直接按 domain。

    :param cache: 缓存后端。
    """

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    async def list_sectors(self) -> list[SectorQuote]:
        """获取行业板块涨跌列表（带缓存）。

        :returns: SectorQuote 列表。
        """
        cache_key = keys.sector_list()
        cached = await self._cache.get(cache_key)
        if cached:
            return [SectorQuote(**item) for item in cached]

        sectors = await self._call_with_fallback("sector", lambda p: p.list_sectors())
        await self._cache.set(cache_key, [s.model_dump() for s in sectors], _TTL_SECTOR_LIST)
        return sectors

    async def get_sector_detail(self, sector_name: str) -> SectorDetail:
        """获取板块详情（行情 + 成分股）。

        :param sector_name: 板块名称。
        :returns: SectorDetail。
        :raises NotFoundError: 板块不存在或数据源全部失败。
        """
        cache_key = keys.sector_detail(sector_name)
        cached = await self._cache.get(cache_key)
        if cached:
            return SectorDetail(**cached)

        # 先取列表找到该板块行情，再取成分股
        sectors = await self.list_sectors()
        quote = next((s for s in sectors if s.name == sector_name), None)
        if quote is None:
            raise NotFoundError(f"sector not found: {sector_name}")

        constituents = await self._call_with_fallback(
            "sector", lambda p: p.get_sector_constituents(sector_name)
        )

        detail = SectorDetail(quote=quote, constituents=constituents)
        await self._cache.set(cache_key, detail.model_dump(), _TTL_SECTOR_DETAIL)
        return detail

    async def _call_with_fallback(self, domain: str, invoker):
        """按 domain 主备优先级调用 Provider。

        :param domain: 领域名。
        :param invoker: 接受 provider 返回 awaitable 的可调用对象。
        :returns: Provider 返回值。
        :raises NotFoundError: 所有数据源均失败。
        """
        candidates = select_providers("A股", domain)  # type: ignore[arg-type]
        if not candidates:
            raise NotFoundError(f"no provider for domain={domain}")

        last_error: Exception | None = None
        for name in candidates:
            provider = _get_provider(name)
            try:
                return await invoker(provider)
            except ProviderError as e:
                logger.warning("provider %s failed for sector: %s", name, e)
                last_error = e
                continue

        raise NotFoundError("sector data unavailable") from last_error
