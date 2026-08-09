"""
@description Provider 领域接口（Protocol）定义，按领域拆分，每个 Provider 只实现能做的领域。
"""

from typing import Protocol, runtime_checkable

from scx_stock.schema.kline import Kline
from scx_stock.schema.stock import Quote, StockInfo


@runtime_checkable
class StockProvider(Protocol):
    """个股领域接口。"""

    async def get_stock(self, code: str) -> StockInfo:
        """获取个股基础信息。

        :param code: 股票代码。
        :returns: StockInfo。
        """
        ...

    async def get_quote(self, code: str) -> Quote:
        """获取个股实时行情。

        :param code: 股票代码。
        :returns: Quote。
        """
        ...


@runtime_checkable
class KlineProvider(Protocol):
    """日 K 线领域接口，供分析引擎消费。"""

    async def get_kline(self, code: str, days: int = 120) -> Kline:
        """获取近 N 个交易日的前复权日 K 线。

        :param code: 证券代码（股票或 ETF）。
        :param days: 返回的最近交易日数量。
        :returns: Kline（按日期升序）。
        """
        ...


@runtime_checkable
class IndexProvider(Protocol):
    """指数领域接口（预留）。"""

    async def get_index(self, code: str):  # pragma: no cover
        """获取指数行情。

        :param code: 指数代码。
        """
        ...
