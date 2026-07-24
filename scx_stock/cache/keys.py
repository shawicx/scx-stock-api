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


def search_result(keyword: str) -> str:
    """搜索结果缓存键。

    :param keyword: 搜索关键词。
    :returns: 缓存键。
    """
    return f"{PREFIX}:search:{keyword}"
