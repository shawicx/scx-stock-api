"""
@description 数据库读写层，封装批量 upsert 与全量加载，供 Scheduler 与搜索索引使用。
"""

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from scx_stock.storage.db import get_session_factory
from scx_stock.storage.models import StockIndustryModel, StockModel

logger = logging.getLogger(__name__)


async def upsert_stocks(rows: Iterable[dict[str, Any]]) -> int:
    """批量 upsert 股票/ETF 列表（PostgreSQL ON CONFLICT）。

    :param rows: 字典迭代，需含 code / name / market / type / pinyin。
    :returns: 写入条数。
    """
    rows = list(rows)
    if not rows:
        return 0

    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(StockModel).values(rows)
        # 冲突按 (code, type) 更新名称、市场、拼音
        update_cols = {
            "name": stmt.excluded.name,
            "market": stmt.excluded.market,
            "pinyin": stmt.excluded.pinyin,
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stock_code_type", set_=update_cols
        )
        await session.execute(stmt)
        await session.commit()

    logger.info("upserted %d stock rows", len(rows))
    return len(rows)


async def load_all_stocks() -> list[StockModel]:
    """全量加载股票/ETF 列表，用于构建搜索索引。

    :returns: StockModel 列表。
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(StockModel))
        return list(result.scalars().all())


async def count_stocks() -> int:
    """统计当前库存股票/ETF 数量。

    :returns: 记录数。
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(func.count()).select_from(StockModel))
        return int(result.scalar_one())


async def clear_all_stocks() -> int:
    """清空 stock 表，用于全量重建（谨慎使用）。

    :returns: 删除条数。
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(delete(StockModel))
        await session.commit()
        return int(result.rowcount or 0)


async def upsert_stock_industries(rows: Iterable[dict[str, Any]]) -> int:
    """批量 upsert 股票行业映射（code → industry）。

    :param rows: 字典迭代，需含 code / industry。
    :returns: 写入条数。
    """
    rows = list(rows)
    if not rows:
        return 0

    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(StockIndustryModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"], set_={"industry": stmt.excluded.industry}
        )
        await session.execute(stmt)
        await session.commit()

    logger.info("upserted %d stock industry rows", len(rows))
    return len(rows)


async def load_all_industries() -> dict[str, str]:
    """全量加载 code → industry 映射，供行情列表零开销补充行业字段。

    :returns: {code: industry} 字典；DB 不可用时返回空字典。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(select(StockIndustryModel))
            return {row.code: row.industry for row in result.scalars().all()}
    except Exception as e:  # noqa: BLE001
        logger.warning("load_all_industries failed: %s", e)
        return {}
