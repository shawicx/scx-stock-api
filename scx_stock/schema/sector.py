"""
@description 板块（行业板块）相关 Pydantic 结构，用于 API 响应与 Provider 返回。
"""

from pydantic import BaseModel


class SectorQuote(BaseModel):
    """行业板块行情条目。

    :param code: 板块代码。
    :param name: 板块名称。
    :param price: 最新价。
    :param change: 涨跌额。
    :param change_pct: 涨跌幅（%）。
    :param total_market_cap: 总市值（元）。
    :param turnover_rate: 换手率（%）。
    :param up_count: 上涨家数。
    :param down_count: 下跌家数。
    :param leading_stock: 领涨股票名称。
    :param leading_stock_change_pct: 领涨股票涨跌幅（%）。
    """

    code: str
    name: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    total_market_cap: float | None = None
    turnover_rate: float | None = None
    up_count: int | None = None
    down_count: int | None = None
    leading_stock: str | None = None
    leading_stock_change_pct: float | None = None


class SectorDetail(BaseModel):
    """板块详情：行情概览 + 成分股列表。

    :param quote: 板块行情概览。
    :param constituents: 成分股列表（代码 + 名称）。
    """

    quote: SectorQuote
    constituents: list[dict[str, str]] = []
