"""
@description sync_jobs 单元测试：用 mock 验证同步流程不依赖外网与 DB。
"""

from unittest.mock import AsyncMock, patch

import pytest

from scx_stock.scheduler import sync_jobs
from scx_stock.schema.stock import StockInfo
from scx_stock.search.index import get_index


@pytest.mark.asyncio
async def test_sync_stock_list_upserts_rows():
    """sync_stock_list 拉取后写入 DB。"""
    fake_items = [
        StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="guizhoumaotai|gzmt", type="stock"),
    ]
    with patch.object(
        sync_jobs.AkshareProvider, "list_stocks", new=AsyncMock(return_value=fake_items)
    ):
        with patch.object(sync_jobs.repo, "upsert_stocks", new=AsyncMock(return_value=1)) as m:
            result = await sync_jobs.sync_stock_list()

    assert result == {"stock_count": 1}
    m.assert_awaited_once()
    rows = m.await_args.args[0]
    assert rows[0]["code"] == "600519"
    assert rows[0]["type"] == "stock"


@pytest.mark.asyncio
async def test_sync_stock_list_handles_provider_error():
    """Provider 失败时返回 0 且不抛异常。"""
    with patch.object(
        sync_jobs.AkshareProvider,
        "list_stocks",
        new=AsyncMock(side_effect=RuntimeError("network")),
    ):
        result = await sync_jobs.sync_stock_list()

    assert result == {"stock_count": 0}


@pytest.mark.asyncio
async def test_sync_stock_list_handles_db_write_error():
    """DB 写入失败时返回 0 且不抛异常（不阻断后续同步步骤）。"""
    fake_items = [
        StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="gz|gzmt", type="stock"),
    ]
    with patch.object(
        sync_jobs.AkshareProvider, "list_stocks", new=AsyncMock(return_value=fake_items)
    ):
        with patch.object(
            sync_jobs.repo,
            "upsert_stocks",
            new=AsyncMock(side_effect=RuntimeError("role postgres does not exist")),
        ):
            result = await sync_jobs.sync_stock_list()

    assert result == {"stock_count": 0}


@pytest.mark.asyncio
async def test_sync_etf_list_handles_db_write_error():
    """ETF 的 DB 写入失败时返回 0 且不抛异常。"""
    fake_items = [
        StockInfo(code="159320", name="电网设备ETF广发", market="深证", pinyin="dianwang|dw", type="etf"),
    ]
    with patch.object(
        sync_jobs.AkshareProvider, "list_etfs", new=AsyncMock(return_value=fake_items)
    ):
        with patch.object(
            sync_jobs.repo,
            "upsert_stocks",
            new=AsyncMock(side_effect=RuntimeError("db connection refused")),
        ):
            result = await sync_jobs.sync_etf_list()

    assert result == {"etf_count": 0}


@pytest.mark.asyncio
async def test_rebuild_search_index_loads_from_db():
    """rebuild_search_index 从 DB 加载并构建索引。"""
    # 模拟 ORM 对象
    class FakeModel:
        def __init__(self, code, name, market, pinyin, type_):
            self.code = code
            self.name = name
            self.market = market
            self.pinyin = pinyin
            self.type = type_

    fake_models = [
        FakeModel("600519", "贵州茅台", "上证", "guizhoumaotai|gzmt", "stock"),
    ]
    with patch.object(sync_jobs.repo, "load_all_stocks", new=AsyncMock(return_value=fake_models)):
        result = await sync_jobs.rebuild_search_index()

    assert result["index_size"] == 1
    assert get_index().size() == 1


@pytest.mark.asyncio
async def test_sync_all_chains_jobs():
    """sync_all 串行执行三个任务并汇总。"""
    with (
        patch.object(sync_jobs, "sync_stock_list", new=AsyncMock(return_value={"stock_count": 2})),
        patch.object(sync_jobs, "sync_etf_list", new=AsyncMock(return_value={"etf_count": 3})),
        patch.object(sync_jobs, "rebuild_search_index", new=AsyncMock(return_value={"index_size": 5})),
    ):
        result = await sync_jobs.sync_all()

    assert result == {"stock_count": 2, "etf_count": 3, "index_size": 5}
