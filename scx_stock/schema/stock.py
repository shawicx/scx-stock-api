"""
@description 个股相关 Pydantic schema，用于 API 请求/响应与 Provider 返回。
"""

from datetime import datetime

from pydantic import BaseModel


class StockInfo:
    """个股基础信息（纯 dataclass 风格占位，后续可改为 Pydantic BaseModel）。

    临时实现使用普通类，避免过早耦合 BaseModel；待 Provider 稳定后统一升级。
    """

    def __init__(
        self,
        code: str,
        name: str,
        market: str,
        industry: str | None = None,
        pinyin: str | None = None,
        type: str | None = None,
    ) -> None:
        self.code = code
        self.name = name
        self.market = market
        self.industry = industry
        self.pinyin = pinyin
        self.type = type


class Quote:
    """个股实时行情。

    :param code: 股票代码。
    :param name: 股票简称。
    :param price: 最新价。
    :param prev_close: 昨收价。
    :param change: 涨跌额。
    :param change_pct: 涨跌幅（%）。
    :param volume: 成交量。
    :param amount: 成交额。
    :param high: 最高价。
    :param low: 最低价。
    :param open: 今开。
    :param timestamp: 行情时间。
    """

    def __init__(
        self,
        code: str,
        name: str,
        price: float | None,
        prev_close: float | None,
        change: float | None,
        change_pct: float | None,
        volume: float | None,
        amount: float | None,
        high: float | None,
        low: float | None,
        open: float | None,
        timestamp: str,
    ) -> None:
        self.code = code
        self.name = name
        self.price = price
        self.prev_close = prev_close
        self.change = change
        self.change_pct = change_pct
        self.volume = volume
        self.amount = amount
        self.high = high
        self.low = low
        self.open = open
        self.timestamp = timestamp

    def to_dict(self) -> dict[str, object]:
        """转字典，便于缓存序列化与 JSON 响应。

        :returns: 字典表示。
        """
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "prev_close": self.prev_close,
            "change": self.change,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "amount": self.amount,
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "timestamp": self.timestamp,
        }


class StockDetailResponse:
    """个股详情聚合响应（行情 + 基础信息），供 API 层使用。

    :param info: 基础信息。
    :param quote: 实时行情。
    :param fetched_at: 聚合时间。
    """

    def __init__(self, info: StockInfo, quote: Quote, fetched_at: datetime | None = None) -> None:
        self.info = info
        self.quote = quote
        self.fetched_at = fetched_at or datetime.now()

    def to_dict(self) -> dict[str, object]:
        """转字典。

        :returns: 字典表示。
        """
        return {
            "info": {
                "code": self.info.code,
                "name": self.info.name,
                "market": self.info.market,
                "industry": self.info.industry,
            },
            "quote": self.quote.to_dict(),
            "fetched_at": self.fetched_at.isoformat(timespec="seconds"),
        }


class StockListItem(BaseModel):
    """股票/ETF 列表行情条目（用于列表/排行接口）。

    :param code: 证券代码。
    :param name: 简称。
    :param market: 市场板块（上证/深证/创业板/科创板/北交所/ETF）。
    :param price: 最新价。
    :param change: 涨跌额。
    :param change_pct: 涨跌幅（%）。
    :param amount: 成交额。
    :param volume: 成交量。
    :param turnover_rate: 换手率（%）。
    :param high: 最高价。
    :param low: 最低价。
    :param open: 今开。
    :param prev_close: 昨收。
    """

    code: str
    name: str
    market: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    amount: float | None = None
    volume: float | None = None
    turnover_rate: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    prev_close: float | None = None
