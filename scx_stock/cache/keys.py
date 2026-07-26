"""
@description 缓存键命名规则集中定义。
"""

# key 前缀
PREFIX = "scx"


def stock_quote(code: str) -> str:
    """个股实时行情缓存键。

    :param code: 股票代码。
    :returns: 缓存键。
    """
    return f"{PREFIX}:stock:quote:{code}"


def stock_list() -> str:
    """股票列表缓存键。

    :returns: 缓存键。
    """
    return f"{PREFIX}:stock:list"


def stock_quote_list(market: str) -> str:
    """股票实时行情列表缓存键。

    :param market: 市场标识（如 "全部"/"上证"）。
    :returns: 缓存键。
    """
    return f"{PREFIX}:stock:quote-list:{market}"


def etf_quote_list() -> str:
    """ETF 实时行情列表缓存键。

    :returns: 缓存键。
    """
    return f"{PREFIX}:etf:quote-list"


def search_result(keyword: str) -> str:
    """搜索结果缓存键。

    :param keyword: 搜索关键词。
    :returns: 缓存键。
    """
    return f"{PREFIX}:search:{keyword}"


def sector_list() -> str:
    """行业板块列表缓存键。

    :returns: 缓存键。
    """
    return f"{PREFIX}:sector:list"


def sector_detail(name: str) -> str:
    """板块详情缓存键。

    :param name: 板块名称。
    :returns: 缓存键。
    """
    return f"{PREFIX}:sector:detail:{name}"


def index_list(group: str) -> str:
    """指数列表缓存键。

    :param group: 指数分组。
    :returns: 缓存键。
    """
    return f"{PREFIX}:index:list:{group}"
