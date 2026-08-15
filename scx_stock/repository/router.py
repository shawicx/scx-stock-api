"""
@description Repository 层，封装 Provider 路由、熔断、降级、缓存编排。
"""

import logging
import re
from datetime import datetime

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


def _strip_code_prefix(code: str) -> str:
    """去掉代码的市场前缀（部分数据源返回 sz300209 形式，统一为纯数字）。

    :param code: 股票代码（可能带 sh/sz/bj 前缀）。
    :returns: 纯数字股票代码。
    """
    return re.sub(r"^(sh|sz|bj)", "", code, flags=re.IGNORECASE)


def _market_of_code(code: str) -> str:
    """按纯数字代码推断市场名（与 Provider 的 _classify_market 规则一致）。

    用于兜底构造 StockInfo：列表项 market 可能为"其他"（带前缀代码误判），
    按剥离前缀后的代码重判更可靠。

    :param code: 纯数字股票代码。
    :returns: 市场名（上证/深证/北交所/其他）。
    """
    if code.startswith("6"):
        return "上证"
    if code.startswith(("0", "3")):
        return "深证"
    if code.startswith(("4", "8")):
        return "北交所"
    return "其他"


class StockRepository:
    """个股领域 Repository，负责选源、降级、缓存。

    :param cache: 缓存后端。
    """

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    async def get_stock(self, code: str) -> StockInfo:
        """获取个股基础信息（带缓存；逐股接口失败时从行情列表兜底）。

        :param code: 股票代码。
        :returns: StockInfo。
        :raises NotFoundError: 代码不存在（逐股接口与行情列表均无此代码）。
        """
        cache_key = f"stock:info:{code}"
        cached = await self._cache.get(cache_key)
        if cached:
            return StockInfo(**cached)

        try:
            info = await self._call_with_fallback(
                "stock", code, lambda p: p.get_stock(code)
            )
        except NotFoundError:
            # 逐股信息接口（stock_individual_info_em）易被限流/抖动，
            # 失败时从全市场行情列表兜底（列表被 /stock/list 轮询保热，含 code/name/market/industry）
            item = await self._lookup_in_quote_list(code)
            info = StockInfo(
                code=code,
                name=item.name,
                market=_market_of_code(code),
                industry=item.industry,
            )
        await self._cache.set(cache_key, _info_to_dict(info), _TTL_STOCK_INFO)
        return info

    async def get_quote(self, code: str) -> Quote:
        """获取个股实时行情（带缓存；逐股接口失败时从行情列表兜底）。

        :param code: 股票代码。
        :returns: Quote。
        :raises NotFoundError: 代码不存在（逐股接口与行情列表均无此代码）。
        """
        cache_key = keys.stock_quote(code)
        cached = await self._cache.get(cache_key)
        if cached:
            return _quote_from_dict(cached)

        try:
            quote = await self._call_with_fallback(
                "stock", code, lambda p: p.get_quote(code)
            )
        except NotFoundError:
            item = await self._lookup_in_quote_list(code)
            quote = Quote(
                code=code,
                name=item.name,
                price=item.price,
                prev_close=item.prev_close,
                change=item.change,
                change_pct=item.change_pct,
                volume=item.volume,
                amount=item.amount,
                high=item.high,
                low=item.low,
                open=item.open,
                timestamp=datetime.now().isoformat(timespec="seconds"),
            )
        await self._cache.set(cache_key, quote.to_dict(), _TTL_QUOTE)
        return quote

    async def _lookup_in_quote_list(self, code: str) -> StockListItem:
        """在全市场行情列表中查找个股（逐股接口失败时的兜底数据源）。

        行情列表被 /stock/list 轮询保热（TTL 120s 缓存），回源时另有
        em/新浪/腾讯三级 fallback，整体比逐股接口稳定。

        :param code: 股票代码（纯数字）。
        :returns: 匹配的 StockListItem。
        :raises NotFoundError: 列表中不存在该代码。
        """
        items = await self.list_stock_quotes()
        for item in items:
            # 部分数据源的列表代码带 sz/sh 前缀，剥离后匹配
            if _strip_code_prefix(item.code) == code:
                return item
        raise NotFoundError(f"stock not found: {code}")

    async def list_stock_quotes(self) -> list[StockListItem]:
        """获取 A 股全市场实时行情列表（带缓存）。

        缓存全量（market=全部），细分板块过滤交由 Service 层。
        回源时从 DB 加载行业映射并注入 Provider。

        :returns: StockListItem 列表。
        """
        cache_key = keys.stock_quote_list("全部")
        cached = await self._cache.get(cache_key)
        if cached:
            return [StockListItem(**item) for item in cached]

        # 行业映射来自 DB（Scheduler 每日同步），DB 不可用时为空
        from scx_stock.storage import repo as _repo

        industry_map = await _repo.load_all_industries()

        items = await self._call_with_fallback(
            "stock", "list",
            lambda p: p.list_stock_quotes(industry_map=industry_map),
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
