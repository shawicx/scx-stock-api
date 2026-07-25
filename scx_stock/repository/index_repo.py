"""
@description 指数 Repository：选源 / 降级 / 缓存编排。
"""

import logging

from scx_stock.cache import keys
from scx_stock.cache.backend import CacheBackend
from scx_stock.config.datasource import select_providers
from scx_stock.exceptions.provider import ProviderError
from scx_stock.exceptions.service import NotFoundError
from scx_stock.repository.router import _get_provider
from scx_stock.schema.index import IndexQuote

logger = logging.getLogger(__name__)

# 指数行情分钟级，TTL 1~5 分钟
_TTL_INDEX_LIST = 120

# 默认展示的"主要大盘指数"白名单（代码 → 显示名），覆盖上证/深证/创业板/科创/北证等
MAJOR_INDEX_CODES: dict[str, str] = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000688": "科创50",
    "899050": "北证50",
    "000300": "沪深300",
    "000905": "中证500",
    "000852": "中证1000",
}


class IndexRepository:
    """指数领域 Repository。

    :param cache: 缓存后端。
    """

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache

    async def list_indexes(self, group: str = "沪深重要指数") -> list[IndexQuote]:
        """获取指数实时行情列表（带缓存）。

        :param group: 指数分组。
        :returns: IndexQuote 列表。
        """
        cache_key = keys.index_list(group)
        cached = await self._cache.get(cache_key)
        if cached:
            return [IndexQuote(**item) for item in cached]

        indexes = await self._call_with_fallback(
            "index", lambda p: p.list_indexes(group)
        )
        await self._cache.set(cache_key, [i.model_dump() for i in indexes], _TTL_INDEX_LIST)
        return indexes

    async def list_major_indexes(self) -> list[IndexQuote]:
        """获取主要大盘指数（白名单过滤）。

        :returns: IndexQuote 列表，按 MAJOR_INDEX_CODES 顺序。
        """
        all_indexes = await self.list_indexes()
        by_code = {i.code: i for i in all_indexes}

        result: list[IndexQuote] = []
        for code, display_name in MAJOR_INDEX_CODES.items():
            q = by_code.get(code)
            if q is not None:
                # 用白名单的显示名，保证稳定
                result.append(q.model_copy(update={"name": display_name}))
        return result

    async def _call_with_fallback(self, domain: str, invoker):
        """按 domain 主备优先级调用 Provider。

        :param domain: 领域名。
        :param invoker: 接受 provider 返回 awaitable 的可调用对象。
        :returns: Provider 返回值。
        :raises NotFoundError: 所有数据源均失败。
        """
        candidates = select_providers("A股", domain)  # type: ignore[arg-type]
        if not candidates:
            raise NotFoundError(f"no provider for domain={domain}")

        last_error: Exception | None = None
        for name in candidates:
            provider = _get_provider(name)
            try:
                return await invoker(provider)
            except ProviderError as e:
                logger.warning("provider %s failed for index: %s", name, e)
                last_error = e
                continue

        raise NotFoundError("index data unavailable") from last_error
