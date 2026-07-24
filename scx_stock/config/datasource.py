"""
@description 数据源能力声明，定义每个 Provider 支持的市场与领域，供 Repository 路由。
"""

from typing import Literal

Market = Literal["A股", "港股", "美股", "指数"]
Domain = Literal["stock", "etf", "sector", "fund_flow", "index", "search"]


class ProviderCapability:
    """单个数据源的能力声明。

    :param name: 数据源名称，如 "akshare"。
    :param markets: 支持的市场列表。
    :param domains: 支持的领域列表。
    """

    def __init__(
        self,
        name: str,
        markets: list[Market],
        domains: list[Domain],
    ) -> None:
        self.name = name
        self.markets = list(markets)
        self.domains = list(domains)

    def supports(self, market: Market, domain: Domain) -> bool:
        """判断是否支持某市场 + 领域组合。

        :param market: 市场标识。
        :param domain: 领域标识。
        :returns: 是否支持。
        """
        return market in self.markets and domain in self.domains


# 能力声明表：可在此扩展更多数据源
CAPABILITIES: list[ProviderCapability] = [
    ProviderCapability(
        "akshare",
        markets=["A股", "港股", "指数"],
        domains=["stock", "etf", "sector", "fund_flow", "index", "search"],
    ),
    ProviderCapability(
        "eastmoney",
        markets=["A股", "港股"],
        domains=["stock", "etf", "sector", "fund_flow"],
    ),
    ProviderCapability(
        "yahoo",
        markets=["美股", "港股", "指数"],
        domains=["stock", "etf", "index"],
    ),
    ProviderCapability(
        "alpha_vantage",
        markets=["美股"],
        domains=["stock", "etf"],
    ),
]


def select_providers(market: Market, domain: Domain) -> list[str]:
    """按市场 + 领域筛选支持的数据源名称，保留声明顺序作为主备优先级。

    :param market: 市场标识。
    :param domain: 领域标识。
    :returns: 数据源名称列表，主源在前。
    """
    return [c.name for c in CAPABILITIES if c.supports(market, domain)]
