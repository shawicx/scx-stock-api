"""
@description 股票列表接口各层单元/集成测试：mock Provider，验证字段映射、缓存、过滤、排序、分页、路由。
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from scx_stock.cache.backend import MemoryCache
from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.repository import router as router_mod
from scx_stock.repository.router import StockRepository
from scx_stock.schema.stock import StockListItem
from scx_stock.service.stock_service import StockService


# ---------- Schema ----------


def test_stock_list_item_defaults_optional():
    """StockListItem 仅 code/name/market 必填，其余字段可选默认 None。"""
    item = StockListItem(code="600519", name="贵州茅台", market="上证")
    assert item.code == "600519"
    assert item.price is None
    assert item.change_pct is None
    assert item.turnover_rate is None


def test_stock_list_item_accepts_all_fields():
    """StockListItem 接受全部行情字段（含主力资金与行业）。"""
    item = StockListItem(
        code="600519", name="贵州茅台", market="上证",
        price=1800.0, change=10.0, change_pct=0.56,
        amount=1e9, volume=123456, turnover_rate=0.5,
        high=1810.0, low=1785.0, open=1795.0, prev_close=1790.0,
        main_net_inflow=5e8, main_net_inflow_pct=2.5, industry="白酒",
    )
    assert item.price == 1800.0
    assert item.change_pct == 0.56
    assert item.main_net_inflow == 5e8
    assert item.main_net_inflow_pct == 2.5
    assert item.industry == "白酒"


# ---------- Provider 字段映射 ----------


@pytest.mark.asyncio
async def test_provider_list_stock_quotes_maps_columns():
    """list_stock_quotes 正确映射 A 股快照 + 资金流 + 行业。"""
    df = pd.DataFrame(
        [
            {
                "代码": "600519",
                "名称": "贵州茅台",
                "最新价": 1800.0,
                "涨跌额": 10.0,
                "涨跌幅": 0.56,
                "成交额": 1_000_000_000,
                "成交量": 123456,
                "换手率": 0.5,
                "最高": 1810.0,
                "最低": 1785.0,
                "今开": 1795.0,
                "昨收": 1790.0,
            }
        ]
    )
    fund_df = pd.DataFrame(
        [
            {
                "代码": "600519",
                "名称": "贵州茅台",
                "今日主力净流入-净额": 500_000_000,
                "今日主力净流入-净占比": 2.5,
            }
        ]
    )
    provider = AkshareProvider()
    with (
        patch("akshare.stock_zh_a_spot_em", return_value=df),
        patch("akshare.stock_individual_fund_flow_rank", return_value=fund_df),
    ):
        result = await provider.list_stock_quotes(
            industry_map={"600519": "白酒"}
        )

    assert len(result) == 1
    item = result[0]
    assert item.code == "600519"
    assert item.name == "贵州茅台"
    assert item.market == "上证"  # 6 开头
    assert item.price == 1800.0
    assert item.change_pct == 0.56
    assert item.amount == 1_000_000_000
    assert item.turnover_rate == 0.5
    assert item.prev_close == 1790.0
    assert item.main_net_inflow == 500_000_000
    assert item.main_net_inflow_pct == 2.5
    assert item.industry == "白酒"


@pytest.mark.asyncio
async def test_provider_list_stock_quotes_fund_flow_failure_tolerant():
    """资金流接口失败时不阻断行情列表（主力资金字段为 None）。"""
    df = pd.DataFrame(
        [{"代码": "600519", "名称": "贵州茅台", "最新价": 1800.0, "涨跌幅": 0.56}]
    )
    provider = AkshareProvider()
    with (
        patch("akshare.stock_zh_a_spot_em", return_value=df),
        patch("akshare.stock_individual_fund_flow_rank", side_effect=Exception("net")),
    ):
        result = await provider.list_stock_quotes()

    assert len(result) == 1
    assert result[0].main_net_inflow is None
    assert result[0].main_net_inflow_pct is None


@pytest.mark.asyncio
async def test_provider_list_etf_quotes_maps_columns():
    """list_etf_quotes 正确映射 ETF 快照列名为 StockListItem（market=ETF）。"""
    df = pd.DataFrame(
        [
            {
                "代码": "510300",
                "名称": "沪深300ETF",
                "最新价": 4.0,
                "涨跌额": 0.02,
                "涨跌幅": 0.5,
                "成交额": 500_000_000,
                "成交量": 9999,
                "换手率": 1.0,
                "最高": 4.02,
                "最低": 3.98,
                "今开": 3.99,
                "昨收": 3.98,
            }
        ]
    )
    provider = AkshareProvider()
    with patch("akshare.fund_etf_spot_em", return_value=df):
        result = await provider.list_etf_quotes()

    assert len(result) == 1
    item = result[0]
    assert item.code == "510300"
    assert item.name == "沪深300ETF"
    assert item.market == "ETF"
    assert item.price == 4.0


@pytest.mark.asyncio
async def test_provider_list_stock_quotes_empty_df():
    """全部数据源返回空 DataFrame 时，validate 校验拦截并抛 ProviderUnavailableError。"""
    import pytest
    from scx_stock.exceptions.provider import ProviderUnavailableError

    provider = AkshareProvider()
    # mock 全部 fallback 源为空（em/sina/tx 三源都会被 validate 判定无效）
    with (
        patch("akshare.stock_zh_a_spot_em", return_value=pd.DataFrame()),
        patch("akshare.stock_zh_a_spot", return_value=pd.DataFrame()),
        patch("akshare.stock_zh_a_spot_tx", return_value=pd.DataFrame()),
    ):
        with pytest.raises(ProviderUnavailableError):
            await provider.list_stock_quotes()


# ---------- 缓存键 ----------


def test_cache_keys_stock_and_etf_quote_list():
    """缓存键命名符合规则。"""
    from scx_stock.cache import keys

    assert keys.stock_quote_list("上证") == "scx:stock:quote-list:上证"
    assert keys.etf_quote_list() == "scx:etf:quote-list"


# ---------- Repository 缓存 ----------


@pytest.mark.asyncio
async def test_repo_list_stock_quotes_caches_result():
    """首次拉取写缓存，二次命中（Provider 只调一次）。"""
    sample = [StockListItem(code="600519", name="贵州茅台", market="上证", price=1800.0)]
    fake_provider = MagicMock()
    fake_provider.list_stock_quotes = AsyncMock(return_value=sample)
    with patch.object(router_mod, "_get_provider", return_value=fake_provider):
        repo = StockRepository(MemoryCache())
        r1 = await repo.list_stock_quotes()
        r2 = await repo.list_stock_quotes()

    assert len(r1) == 1 and r1[0].code == "600519"
    assert fake_provider.list_stock_quotes.await_count == 1  # 二次命中缓存
    assert r2[0].price == 1800.0


@pytest.mark.asyncio
async def test_repo_list_etf_quotes_caches_result():
    """ETF 列表首次拉取写缓存，二次命中。"""
    sample = [StockListItem(code="510300", name="沪深300ETF", market="ETF", price=4.0)]
    fake_provider = MagicMock()
    fake_provider.list_etf_quotes = AsyncMock(return_value=sample)
    with patch.object(router_mod, "_get_provider", return_value=fake_provider):
        repo = StockRepository(MemoryCache())
        r1 = await repo.list_etf_quotes()
        r2 = await repo.list_etf_quotes()

    assert len(r1) == 1 and r1[0].code == "510300"
    assert fake_provider.list_etf_quotes.await_count == 1
    assert r2[0].market == "ETF"


# ---------- Service 过滤 / 排序 / 分页 ----------


def _make_repo_mock(stocks=None, etfs=None):
    """构造 mock StockRepository。"""
    repo = MagicMock()
    repo.list_stock_quotes = AsyncMock(return_value=stocks or [])
    repo.list_etf_quotes = AsyncMock(return_value=etfs or [])
    return repo


@pytest.mark.asyncio
async def test_service_filter_by_market_chuangyeban():
    """market=创业板 只返回 300 开头。"""
    stocks = [
        StockListItem(code="600519", name="茅台", market="上证", change_pct=1.0),
        StockListItem(code="300750", name="宁德", market="深证", change_pct=2.0),
        StockListItem(code="000001", name="平安", market="深证", change_pct=0.5),
        StockListItem(code="688981", name="中芯", market="上证", change_pct=3.0),
    ]
    service = StockService(_make_repo_mock(stocks=stocks), MemoryCache())
    items, total = await service.list_stocks(
        market="创业板", type_="stock", sort_by="change_pct",
        descending=True, page=1, page_size=20,
    )
    assert total == 1
    assert items[0].code == "300750"


@pytest.mark.asyncio
async def test_service_filter_by_market_kechuangban():
    """market=科创板 只返回 688 开头。"""
    stocks = [
        StockListItem(code="688981", name="中芯", market="上证", change_pct=3.0),
        StockListItem(code="600519", name="茅台", market="上证", change_pct=1.0),
    ]
    service = StockService(_make_repo_mock(stocks=stocks), MemoryCache())
    items, total = await service.list_stocks(
        market="科创板", type_="stock", sort_by="change_pct",
        descending=False, page=1, page_size=20,
    )
    assert total == 1
    assert items[0].code == "688981"


@pytest.mark.asyncio
async def test_service_sort_desc_with_none_last():
    """change_pct 降序，None 值排末尾。"""
    stocks = [
        StockListItem(code="A", name="A", market="上证", change_pct=None),
        StockListItem(code="B", name="B", market="上证", change_pct=1.0),
        StockListItem(code="C", name="C", market="上证", change_pct=3.0),
    ]
    service = StockService(_make_repo_mock(stocks=stocks), MemoryCache())
    items, total = await service.list_stocks(
        market="全部", type_="stock", sort_by="change_pct",
        descending=True, page=1, page_size=20,
    )
    assert [i.code for i in items] == ["C", "B", "A"]
    assert total == 3


@pytest.mark.asyncio
async def test_service_pagination():
    """内存分页：total 正确，返回当前页切片。"""
    stocks = [
        StockListItem(code=f"60000{i}", name=f"N{i}", market="上证", change_pct=float(i))
        for i in range(5)
    ]
    service = StockService(_make_repo_mock(stocks=stocks), MemoryCache())
    items, total = await service.list_stocks(
        market="全部", type_="stock", sort_by="change_pct",
        descending=True, page=2, page_size=2,
    )
    assert total == 5
    assert len(items) == 2
    # 降序后 [4,3,2,1,0]，第 2 页 = [2,1]
    assert [i.code for i in items] == ["600002", "600001"]


@pytest.mark.asyncio
async def test_service_type_etf_ignores_market():
    """type=etf 时忽略 market，返回 ETF 全量。"""
    etfs = [StockListItem(code="510300", name="300ETF", market="ETF", price=4.0)]
    stocks = [StockListItem(code="600519", name="茅台", market="上证")]
    service = StockService(_make_repo_mock(stocks=stocks, etfs=etfs), MemoryCache())
    items, total = await service.list_stocks(
        market="上证", type_="etf", sort_by="change_pct",
        descending=True, page=1, page_size=20,
    )
    assert total == 1
    assert items[0].code == "510300"


@pytest.mark.asyncio
async def test_service_type_all_merges_stock_and_etf():
    """type=all 合并股票与 ETF（market=全部 时不按板块过滤 ETF）。"""
    stocks = [StockListItem(code="600519", name="茅台", market="上证", change_pct=1.0)]
    etfs = [StockListItem(code="510300", name="300ETF", market="ETF", change_pct=2.0)]
    service = StockService(_make_repo_mock(stocks=stocks, etfs=etfs), MemoryCache())
    items, total = await service.list_stocks(
        market="全部", type_="all", sort_by="change_pct",
        descending=True, page=1, page_size=20,
    )
    assert total == 2
    assert [i.code for i in items] == ["510300", "600519"]


# ---------- API 集成 ----------


@pytest.fixture(scope="module")
def client():
    from scx_stock.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_stock_list_route_mounted(client):
    """/stock/list 路由已挂载，且不被 /stock/{code} 吞掉。"""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/stock/list" in paths
    assert "/api/v1/stock/{code}" in paths  # 两者共存


def test_stock_list_invalid_market_returns_422(client):
    """非法 market 枚举返回 422。"""
    resp = client.get("/api/v1/stock/list", params={"market": "美股"})
    assert resp.status_code == 422
    assert resp.json()["code"] == 42201


def test_stock_list_invalid_type_returns_422(client):
    """非法 type 枚举返回 422。"""
    resp = client.get("/api/v1/stock/list", params={"type": "bond"})
    assert resp.status_code == 422


def test_stock_list_page_ge_1(client):
    """page < 1 返回 422。"""
    resp = client.get("/api/v1/stock/list", params={"page": 0})
    assert resp.status_code == 422
