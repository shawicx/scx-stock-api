"""
@description K 线数据模型，供 Provider 返回与分析引擎消费。
"""

from datetime import date

from pydantic import BaseModel


class KlineBar(BaseModel):
    """单根日 K 线（前复权）。

    :param trade_date: 交易日期。
    :param open: 开盘价。
    :param close: 收盘价。
    :param high: 最高价。
    :param low: 最低价。
    :param volume: 成交量。
    """

    trade_date: date
    open: float
    close: float
    high: float
    low: float
    volume: float


class Kline(BaseModel):
    """某标的的日 K 线序列。

    :param code: 证券代码。
    :param name: 简称（可能为空）。
    :param bars: 按日期升序排列的 K 线条目。
    """

    code: str
    name: str = ""
    bars: list[KlineBar]
