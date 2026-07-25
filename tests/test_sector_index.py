"""
@description 板块与指数领域单元测试：mock Provider，验证字段映射、缓存、排序、API。
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from scx_stock.cache.backend import MemoryCache
from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.repository import sector_repo as sector_repo_mod
from scx_stock.repository import index_repo as index_repo_mod
from scx_stock.repository.index_repo import IndexRepository
from scx_stock.repository.sector_repo import SectorRepository
from scx_stock.schema.index import IndexQuote
from scx_stock.schema.sector import SectorQuote
from scx_stock.service.index_service import IndexService
from scx_stock.service.sector_service import SectorService


# ---------- Provider 字段映射 ----------


@pytest.mark.asyncio
async def test_provider_list_sectors_maps_columns():
    """list_sectors 正确映射东方财富列名。"""
    df = pd.DataFrame(
        [
            {
                "板块代码": "BK0479",
                "板块名称": "小金属",
                "最新价": 1000.5,
                "涨跌额": 20.5,
                "涨跌幅": 2.09,
                "总市值": 5_000_000_000,
                "换手率": 3.5,
                "上涨家数": 80,
                "下跌家数": 10,
                "领涨股票": "某股票",
                "领涨股票-涨跌幅": 10.0,
            }
        ]
    )
    provider = AkshareProvider()
    with patch("akshare.stock_board_industry_name_em", return_value=df):
        result = await provider.list_sectors()

    assert len(result) == 1
    s = result[0]
    assert s.code == "BK0479"
    assert s.name == "小金属"
    assert s.price == 1000.5
    assert s.change_pct == 2.09
    assert s.up_count == 80
    assert s.down_count == 10
    assert s.leading_stock == "某股票"


@pytest.mark.asyncio
async def test_provider_list_indexes_maps_columns():
    """list_indexes 正确映射东方财富指数列名。"""
    df = pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "上证指数",
                "最新价": 3000.0,
                "涨跌幅": 1.5,
                "涨跌额": 45.0,
                "成交量": 100_000_000,
                "成交额": 200_000_000_000,
                "振幅": 2.0,
                "最高": 3010.0,
                "最低": 2980.0,
                "今开": 2990.0,
                "昨收": 2955.0,
            }
        ]
    )
    provider = AkshareProvider()
    with patch("akshare.stock_zh_index_spot_em", return_value=df):
        result = await provider.list_indexes("沪深重要指数")

    assert len(result) == 1
    i = result[0]
    assert i.code == "000001"
    assert i.name == "上证指数"
    assert i.price == 3000.0
    assert i.change_pct == 1.5
    assert i.prev_close == 2955.0


# ---------- Repository 缓存 ----------


@pytest.mark.asyncio
async def test_sector_repository_caches_list():
    """板块列表首次拉取后写缓存，二次命中。"""
    sample = [SectorQuote(code="BK1", name="板块A", change_pct=1.5)]
    fake_provider = MagicMock()
    fake_provider.list_sectors = AsyncMock(return_value=sample)
    with patch.object(sector_repo_mod, "_get_provider", return_value=fake_provider):
        repo = SectorRepository(MemoryCache())
        r1 = await repo.list_sectors()
        r2 = await repo.list_sectors()

    assert len(r1) == 1
    assert r1[0].code == "BK1"
    assert fake_provider.list_sectors.await_count == 1  # 二次命中缓存
    assert r2[0].code == "BK1"


@pytest.mark.asyncio
async def test_index_repository_major_filter():
    """list_major_indexes 按白名单过滤并按声明顺序输出。"""
    all_indexes = [
        IndexQuote(code="399001", name="深证成指", price=10000),
        IndexQuote(code="000001", name="上证指数", price=3000),
        IndexQuote(code="999999", name="其他指数", price=100),  # 不在白名单
    ]
    fake_provider = MagicMock()
    fake_provider.list_indexes = AsyncMock(return_value=all_indexes)
    with patch.object(index_repo_mod, "_get_provider", return_value=fake_provider):
        repo = IndexRepository(MemoryCache())
        result = await repo.list_major_indexes()

    codes = [i.code for i in result]
    assert codes == ["000001", "399001"]  # 白名单顺序，过滤掉 999999
    assert result[0].name == "上证指数"  # 用白名单显示名


# ---------- Service 排序 ----------


@pytest.mark.asyncio
async def test_sector_service_sort_by_change_pct_desc():
    """Service 按涨跌幅降序排列。"""
    sectors = [
        SectorQuote(code="A", name="A", change_pct=1.0),
        SectorQuote(code="B", name="B", change_pct=3.0),
        SectorQuote(code="C", name="C", change_pct=2.0),
    ]
    repo = MagicMock()
    repo.list_sectors = AsyncMock(return_value=sectors)
    service = SectorService(repo, MemoryCache())

    result = await service.list_sectors(sort_by="change_pct", descending=True)
    assert [s.code for s in result] == ["B", "C", "A"]


@pytest.mark.asyncio
async def test_sector_service_none_value_sorted_last():
    """None 值的条目排到最后（容错）。"""
    sectors = [
        SectorQuote(code="A", name="A", change_pct=None),
        SectorQuote(code="B", name="B", change_pct=1.0),
    ]
    repo = MagicMock()
    repo.list_sectors = AsyncMock(return_value=sectors)
    service = SectorService(repo, MemoryCache())

    result = await service.list_sectors(descending=True)
    assert [s.code for s in result] == ["B", "A"]


# ---------- API 集成 ----------


@pytest.fixture(scope="module")
def client():
    from scx_stock.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_sector_and_market_routes_mounted(client):
    """板块与指数路由已挂载。"""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/sector/list" in paths
    assert "/api/v1/sector/{name}" in paths
    assert "/api/v1/market/index" in paths
    assert "/api/v1/market/index/all" in paths
