"""
@description 个股业务编排层，聚合基础信息与实时行情，不感知数据源。
"""

import asyncio
import logging

from scx_stock.cache.backend import CacheBackend
from scx_stock.exceptions.service import NotFoundError
from scx_stock.repository.router import StockRepository
from scx_stock.schema.stock import StockDetailResponse

logger = logging.getLogger(__name__)


class StockService:
    """个股业务 Service。

    :param repo: StockRepository 实例。
    :param cache: 缓存后端（预留用于聚合结果缓存）。
    """

    def __init__(self, repo: StockRepository, cache: CacheBackend) -> None:
        self._repo = repo
        self._cache = cache

    async def get_detail(self, code: str) -> StockDetailResponse:
        """获取个股详情（基础信息 + 实时行情聚合）。

        :param code: 股票代码。
        :returns: StockDetailResponse。
        :raises NotFoundError: 代码不存在或数据源全部失败。
        """
        try:
            info, quote = await asyncio.gather(
                self._repo.get_stock(code),
                self._repo.get_quote(code),
            )
        except Exception:  # noqa: BLE001
            logger.exception("get_detail failed for %s", code)
            raise

        return StockDetailResponse(info=info, quote=quote)
