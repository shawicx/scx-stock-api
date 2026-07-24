"""
@description Provider 领域接口（Protocol）定义，按领域拆分，每个 Provider 只实现能做的领域。
"""

from typing import Protocol, runtime_checkable

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
class IndexProvider(Protocol):
    """指数领域接口（预留）。"""

    async def get_index(self, code: str):  # pragma: no cover
        """获取指数行情。

        :param code: 指数代码。
        """
        ...
