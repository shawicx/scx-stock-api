"""
@description Repository 层，封装 Provider 路由、熔断、降级、缓存编排。
"""

import logging

from scx_stock.cache import keys
from scx_stock.cache.backend import CacheBackend, get_cache
from scx_stock.config.datasource import select_providers
from scx_stock.exceptions.provider import ProviderError
from scx_stock.exceptions.service import NotFoundError
from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.provider.base import SyncProviderBase
from scx_stock.schema.stock import Quote, StockInfo, StockListItem

logger = logging.getLogger(__name__)

# 各领域缓存 TTL（秒），与持久化策略表一致
_TTL_QUOTE = 30
_TTL_STOCK_INFO = 300
_TTL_QUOTE_LIST = 120  # 行情列表分钟级，与板块/指数一致


# 数据源注册表：name -> provider 实例（懒加载）
_providers: dict[str, SyncProviderBase] = {}


def _get_provider(name: str) -> SyncProviderBase:
    """按名称获取 Provider 实例（懒加载单例）。

    :param name: 数据源名称。
    :returns: Provider 实例。
    :raises ProviderError: 未注册的数据源。
    """
    if name not in _providers:
        if name == "akshare":
            _providers[name] = AkshareProvider()
        else:
            # 其他 provider 暂未实现，统一回退到 akshare
            _providers[name] = AkshareProvider()
    return _providers[name]


def _classify_market(code: str) -> str:
    """按代码识别市场（用于路由）。

    :param code: 股票代码。
    :returns: 市场名。
    """
    if not code:
        return "A股"
    # 字母开头 → 美股
    if code[0].isalpha():
        return "美股"
    return "A股"


class StockRepository:
    """个股领域 Repository，负责选源、降级、缓存。

    :param cache: 缓存后端。
    """

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    async def get_stock(self, code: str) -> StockInfo:
        """获取个股基础信息（带缓存）。

        :param code: 股票代码。
        :returns: StockInfo。
        :raises NotFoundError: 代码不存在。
        """
        cache_key = f"stock:info:{code}"
        cached = await self._cache.get(cache_key)
        if cached:
            return StockInfo(**cached)

        info = await self._call_with_fallback(
            "stock", code, lambda p: p.get_stock(code)
        )
        await self._cache.set(cache_key, _info_to_dict(info), _TTL_STOCK_INFO)
        return info

    async def get_quote(self, code: str) -> Quote:
        """获取个股实时行情（带缓存）。

        :param code: 股票代码。
        :returns: Quote。
        :raises NotFoundError: 代码不存在。
        """
        cache_key = keys.stock_quote(code)
        cached = await self._cache.get(cache_key)
        if cached:
            return _quote_from_dict(cached)

        quote = await self._call_with_fallback(
            "stock", code, lambda p: p.get_quote(code)
        )
        await self._cache.set(cache_key, quote.to_dict(), _TTL_QUOTE)
        return quote

    async def list_stock_quotes(self) -> list[StockListItem]:
        """获取 A 股全市场实时行情列表（带缓存）。

        缓存全量（market=全部），细分板块过滤交由 Service 层。

        :returns: StockListItem 列表。
        """
        cache_key = keys.stock_quote_list("全部")
        cached = await self._cache.get(cache_key)
        if cached:
            return [StockListItem(**item) for item in cached]

        items = await self._call_with_fallback(
            "stock", "list", lambda p: p.list_stock_quotes()
        )
        await self._cache.set(
            cache_key, [i.model_dump() for i in items], _TTL_QUOTE_LIST
        )
        return items

    async def list_etf_quotes(self) -> list[StockListItem]:
        """获取全量 ETF 实时行情列表（带缓存）。

        :returns: StockListItem 列表。
        """
        cache_key = keys.etf_quote_list()
        cached = await self._cache.get(cache_key)
        if cached:
            return [StockListItem(**item) for item in cached]

        items = await self._call_with_fallback(
            "stock", "list", lambda p: p.list_etf_quotes()
        )
        await self._cache.set(
            cache_key, [i.model_dump() for i in items], _TTL_QUOTE_LIST
        )
        return items

    async def _call_with_fallback(self, domain: str, code: str, invoker):
        """按主备优先级调用 Provider，全部失败抛 NotFoundError。

        :param domain: 领域名。
        :param code: 股票代码。
        :param invoker: 接受 provider 返回 awaitable 的可调用对象。
        :returns: Provider 返回值。
        :raises NotFoundError: 所有数据源均失败。
        """
        market = _classify_market(code)
        candidates = select_providers(market, domain)  # type: ignore[arg-type]
        if not candidates:
            raise NotFoundError(f"no provider for market={market} domain={domain}")

        last_error: Exception | None = None
        for name in candidates:
            provider = _get_provider(name)
            try:
                return await invoker(provider)
            except ProviderError as e:
                logger.warning("provider %s failed for %s: %s", name, code, e)
                last_error = e
                continue

        raise NotFoundError(f"stock not found: {code}") from last_error


def _info_to_dict(info: StockInfo) -> dict[str, object]:
    """StockInfo 转字典。

    :param info: StockInfo 对象。
    :returns: 字典表示。
    """
    return {
        "code": info.code,
        "name": info.name,
        "market": info.market,
        "industry": info.industry,
        "pinyin": info.pinyin,
    }


def _quote_from_dict(d: dict[str, object]) -> Quote:
    """从字典重建 Quote。

    :param d: 字典表示。
    :returns: Quote 对象。
    """
    return Quote(**d)  # type: ignore[arg-type]
