"""
@description Repository 层单元测试：用 mock 验证缓存命中、降级、字段映射，不依赖外网。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from scx_stock.cache.backend import MemoryCache
from scx_stock.repository import router as router_mod
from scx_stock.repository.router import StockRepository
from scx_stock.schema.stock import Quote, StockInfo


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
