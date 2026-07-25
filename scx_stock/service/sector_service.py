"""
@description 板块业务编排层。
"""

import logging

from scx_stock.cache.backend import CacheBackend
from scx_stock.repository.sector_repo import SectorRepository
from scx_stock.schema.sector import SectorDetail, SectorQuote

logger = logging.getLogger(__name__)


class SectorService:
    """板块业务 Service。

    :param repo: SectorRepository 实例。
    :param cache: 缓存后端（预留聚合缓存）。
    """

    def __init__(self, repo: SectorRepository, cache: CacheBackend) -> None:
        self._repo = repo
        self._cache = cache

    async def list_sectors(
        self, sort_by: str = "change_pct", descending: bool = True, limit: int = 50
    ) -> list[SectorQuote]:
        """获取板块涨跌排行。

        :param sort_by: 排序字段，change_pct / turnover_rate / total_market_cap。
        :param descending: 是否降序。
        :param limit: 最大返回数。
        :returns: SectorQuote 列表。
        """
        sectors = await self._repo.list_sectors()

        # None 值始终排到最后（不受 descending 影响）
        has_value = [s for s in sectors if getattr(s, sort_by) is not None]
        none_list = [s for s in sectors if getattr(s, sort_by) is None]
        has_value.sort(key=lambda s: getattr(s, sort_by), reverse=descending)
        return (has_value + none_list)[:limit]

    async def get_sector_detail(self, sector_name: str) -> SectorDetail:
        """获取板块详情。

        :param sector_name: 板块名称。
        :returns: SectorDetail。
        """
        return await self._repo.get_sector_detail(sector_name)
