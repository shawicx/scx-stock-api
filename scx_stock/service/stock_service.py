"""
@description 个股业务编排层，聚合基础信息与实时行情，不感知数据源。
"""

import asyncio
import logging

from scx_stock.cache.backend import CacheBackend
from scx_stock.exceptions.service import NotFoundError
from scx_stock.repository.router import StockRepository
from scx_stock.schema.stock import StockDetailResponse, StockListItem

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

    async def list_stocks(
        self,
        market: str,
        type_: str,
        sort_by: str,
        descending: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[StockListItem], int]:
        """获取股票/ETF 行情列表（过滤 + 排序 + 内存分页）。

        :param market: 市场板块（上证/深证/创业板/科创板/北交所/全部）。
        :param type_: 证券类型 stock/etf/all。
        :param sort_by: 排序字段 change_pct/amount/turnover_rate。
        :param descending: 是否降序。
        :param page: 页码（从 1 起）。
        :param page_size: 每页条数。
        :returns: (当前页条目列表, 总条数)。
        """
        # 1. 按类型拉取数据源
        if type_ == "etf":
            items = await self._repo.list_etf_quotes()
            # ETF 不按板块细分，忽略 market
        elif type_ == "all":
            stocks, etfs = await asyncio.gather(
                self._repo.list_stock_quotes(),
                self._repo.list_etf_quotes(),
            )
            if market != "全部":
                # type=all 且指定板块：仅过滤股票部分，ETF 全保留
                items = self._filter_by_market(stocks, market) + list(etfs)
            else:
                items = list(stocks) + list(etfs)
        else:  # stock
            items = await self._repo.list_stock_quotes()
            if market != "全部":
                items = self._filter_by_market(items, market)

        # 2. 排序：None 排末尾（不受 descending 影响）
        has_value = [i for i in items if getattr(i, sort_by) is not None]
        none_list = [i for i in items if getattr(i, sort_by) is None]
        has_value.sort(key=lambda i: getattr(i, sort_by), reverse=descending)
        sorted_items = has_value + none_list

        # 3. 内存分页
        total = len(sorted_items)
        start = (page - 1) * page_size
        end = start + page_size
        return sorted_items[start:end], total

    @staticmethod
    def _filter_by_market(
        items: list[StockListItem], market: str
    ) -> list[StockListItem]:
        """按市场板块细分过滤（基于代码前缀）。

        :param items: 待过滤列表。
        :param market: 板块名（上证/深证/创业板/科创板/北交所）。
        :returns: 过滤后列表。
        """
        if market == "全部":
            return items

        def _match(code: str, m: str) -> bool:
            if m == "上证":
                return code.startswith("6") and not code.startswith("688")
            if m == "深证":
                return code.startswith("0")
            if m == "创业板":
                return code.startswith("300")
            if m == "科创板":
                return code.startswith("688")
            if m == "北交所":
                return code.startswith("8") or code.startswith("4")
            return True

        return [i for i in items if _match(i.code, market)]
