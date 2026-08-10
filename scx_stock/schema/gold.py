"""
@description 黄金行情数据模型，用于沪金期货、上金所现货等品种的行情展示。
"""

from pydantic import BaseModel


class GoldQuote(BaseModel):
    """黄金品种实时行情。

    :param code: 品种代码（如 AU0 / Au99.99 / NYAuTN06）。
    :param name: 品种名称（如 沪金主连 / 上金所Au99.99 / 纽约金TN06）。
    :param category: 分类：futures_shfe（上期所期货）/ spot_sge（上金所现货）/ comex_proxy（纽约金跟踪）。
    :param price: 最新价。
    :param change: 涨跌额。
    :param change_pct: 涨跌幅（%）。
    :param prev_close: 昨收价。
    :param prev_settlement: 前结算价（期货独有）。
    :param open: 今开。
    :param high: 最高。
    :param low: 最低。
    :param volume: 成交量。
    :param position: 持仓量（期货独有）。
    :param timestamp: 行情时间。
    """

    code: str
    name: str
    category: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    prev_close: float | None = None
    prev_settlement: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    position: float | None = None
    timestamp: str | None = None
