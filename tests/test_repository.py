"""
@description Repository 层单元测试：用 mock 验证缓存命中、降级、字段映射，不依赖外网。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from scx_stock.cache.backend import MemoryCache
from scx_stock.exceptions.provider import ProviderError
from scx_stock.exceptions.service import NotFoundError
from scx_stock.repository import router as router_mod
from scx_stock.repository.router import StockRepository
from scx_stock.schema.stock import Quote, StockInfo, StockListItem


@pytest.fixture
def cache():
    return MemoryCache()


@pytest.fixture
def repo(cache):
    return StockRepository(cache)


@pytest.mark.asyncio
async def test_get_quote_caches_result(repo, monkeypatch):
    """首次拉取写入缓存，第二次命中缓存不再调 Provider。"""
    sample = Quote(
        code="600519",
        name="贵州茅台",
        price=1800.0,
        prev_close=1790.0,
        change=10.0,
        change_pct=0.56,
        volume=123456,
        amount=1000000,
        high=1810.0,
        low=1785.0,
        open=1795.0,
        timestamp="2026-07-25T10:00:00",
    )

    fake_provider = MagicMock()
    fake_provider.get_quote = AsyncMock(return_value=sample)
    monkeypatch.setattr(router_mod, "_providers", {"akshare": fake_provider})

    # 首次：调用 Provider
    q1 = await repo.get_quote("600519")
    assert q1.price == 1800.0
    assert fake_provider.get_quote.await_count == 1

    # 第二次：命中缓存，不再调 Provider
    q2 = await repo.get_quote("600519")
    assert q2.price == 1800.0
    assert fake_provider.get_quote.await_count == 1  # 未增加


@pytest.mark.asyncio
async def test_get_stock_maps_dict_to_obj(repo, monkeypatch):
    """get_stock 缓存字典，重建为 StockInfo。"""
    sample = StockInfo(code="000001", name="平安银行", market="深证", industry="银行")

    fake_provider = MagicMock()
    fake_provider.get_stock = AsyncMock(return_value=sample)
    monkeypatch.setattr(router_mod, "_providers", {"akshare": fake_provider})

    info = await repo.get_stock("000001")
    assert info.code == "000001"
    assert info.name == "平安银行"
    assert info.market == "深证"


def _failing_provider(method: str, message: str) -> MagicMock:
    """构造指定方法必失败的 Provider mock（模拟上游限流/不可用）。"""
    fake = MagicMock()
    setattr(fake, method, AsyncMock(side_effect=ProviderError(message)))
    return fake


def _list_item(**overrides) -> StockListItem:
    """构造行情列表条目（字段可覆盖）。"""
    fields = dict(
        code="sz002628",
        name="示例股份",
        market="其他",
        price=10.0,
        change=0.1,
        change_pct=1.0,
        amount=1.2e8,
        volume=9.9e6,
        turnover_rate=5.5,
        high=10.2,
        low=9.9,
        open=10.0,
        prev_close=9.9,
        main_net_inflow=2.3e7,
        main_net_inflow_pct=1.2,
        industry="计算机",
    )
    fields.update(overrides)
    return StockListItem(**fields)


@pytest.mark.asyncio
async def test_get_stock_falls_back_to_quote_list(repo, monkeypatch):
    """逐股信息接口全部失败时，从行情列表兜底构造 StockInfo。"""
    failing = _failing_provider("get_stock", "akshare stock info unavailable: 002628")
    monkeypatch.setattr(
        router_mod, "_providers", {"akshare": failing, "eastmoney": failing}
    )
    monkeypatch.setattr(
        repo, "list_stock_quotes", AsyncMock(return_value=[_list_item()])
    )

    info = await repo.get_stock("002628")
    assert info.code == "002628"
    assert info.name == "示例股份"
    assert info.market == "深证"  # 列表项带 sz 前缀被误判为"其他"，按代码重判
    assert info.industry == "计算机"


@pytest.mark.asyncio
async def test_get_quote_falls_back_to_quote_list(repo, monkeypatch):
    """逐股行情接口全部失败时，从行情列表兜底构造 Quote。"""
    failing = _failing_provider("get_quote", "all sources failed")
    monkeypatch.setattr(
        router_mod, "_providers", {"akshare": failing, "eastmoney": failing}
    )
    monkeypatch.setattr(
        repo,
        "list_stock_quotes",
        AsyncMock(return_value=[_list_item(code="600519", market="上证")]),
    )

    quote = await repo.get_quote("600519")
    assert quote.code == "600519"
    assert quote.name == "示例股份"
    assert quote.price == 10.0
    assert quote.prev_close == 9.9

    # 兜底结果同样写缓存：第二次不再触发列表查找
    list_mock = repo.list_stock_quotes
    quote2 = await repo.get_quote("600519")
    assert quote2.price == 10.0
    assert list_mock.await_count == 1  # 未增加


@pytest.mark.asyncio
async def test_get_stock_raises_when_quote_list_has_no_code(repo, monkeypatch):
    """逐股接口失败且行情列表中也无此代码时，抛 NotFoundError。"""
    failing = _failing_provider("get_stock", "akshare stock info unavailable: 300999")
    monkeypatch.setattr(
        router_mod, "_providers", {"akshare": failing, "eastmoney": failing}
    )
    monkeypatch.setattr(repo, "list_stock_quotes", AsyncMock(return_value=[]))

    with pytest.raises(NotFoundError):
        await repo.get_stock("300999")
