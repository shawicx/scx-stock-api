"""
@description 大盘指数相关 Pydantic 结构，用于 API 响应与 Provider 返回。
"""

from pydantic import BaseModel


class IndexQuote(BaseModel):
    """指数实时行情条目。

    :param code: 指数代码（如 000001）。
    :param name: 指数名称（如 上证指数）。
    :param price: 最新价。
    :param change_pct: 涨跌幅（%）。
    :param change: 涨跌额。
    :param volume: 成交量。
    :param amount: 成交额。
    :param amplitude: 振幅（%）。
    :param high: 最高。
    :param low: 最低。
    :param open: 今开。
    :param prev_close: 昨收。
    """

    code: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    change: float | None = None
    volume: float | None = None
    amount: float | None = None
    amplitude: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    prev_close: float | None = None
