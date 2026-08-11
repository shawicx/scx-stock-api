"""
@description 数据库读写层，封装批量 upsert 与全量加载，供 Scheduler 与搜索索引使用。
"""

import logging
from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from scx_stock.schema.analysis import AnalysisReport
from scx_stock.schema.kline import Kline, KlineBar
from scx_stock.storage.db import get_session_factory
from scx_stock.storage.models import (
    AnalysisReportModel,
    AppSettingModel,
    KlineModel,
    MarketCalendarModel,
    StockIndustryModel,
    StockModel,
    WatchlistModel,
)

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


# ---------------------------------------------------------------------------
# 应用配置（app_setting）
# ---------------------------------------------------------------------------


async def get_all_settings() -> dict[str, str]:
    """全量加载应用配置为 {key: value} 字典。

    DB 不可用时返回空字典（调用方回退 .env）。

    :returns: {key: value} 字典。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(select(AppSettingModel))
            return {row.key: row.value for row in result.scalars().all()}
    except Exception as e:  # noqa: BLE001
        logger.warning("get_all_settings failed: %s", e)
        return {}


async def upsert_settings(items: dict[str, str]) -> int:
    """批量 upsert 应用配置。

    :param items: {key: value} 字典。
    :returns: 写入条数。
    """
    if not items:
        return 0
    rows = [{"key": k, "value": v} for k, v in items.items()]
    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(AppSettingModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"], set_={"value": stmt.excluded.value}
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# 关注列表（watchlist）
# ---------------------------------------------------------------------------


async def list_watchlist() -> list[WatchlistModel]:
    """全量加载关注列表，按 sort_order 升序。

    :returns: WatchlistModel 列表。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(WatchlistModel).order_by(WatchlistModel.sort_order)
            )
            return list(result.scalars().all())
    except Exception as e:  # noqa: BLE001
        logger.warning("list_watchlist failed: %s", e)
        return []


async def list_watchlist_codes() -> list[str]:
    """仅返回关注列表的代码集合。

    :returns: 代码列表。
    """
    models = await list_watchlist()
    return [m.code for m in models]


async def add_watchlist(code: str, name: str = "", sort_order: int = 0) -> None:
    """添加关注（已存在则更新名称/排序）。

    :param code: 证券代码。
    :param name: 简称。
    :param sort_order: 排序序号。
    """
    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(WatchlistModel).values(
            code=code, name=name, sort_order=sort_order
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={"name": stmt.excluded.name, "sort_order": stmt.excluded.sort_order},
        )
        await session.execute(stmt)
        await session.commit()


async def remove_watchlist(code: str) -> int:
    """移除关注。

    :param code: 证券代码。
    :returns: 删除条数。
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            delete(WatchlistModel).where(WatchlistModel.code == code)
        )
        await session.commit()
        return int(result.rowcount or 0)


async def clear_watchlist() -> int:
    """清空关注列表。

    :returns: 删除条数。
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(delete(WatchlistModel))
        await session.commit()
        return int(result.rowcount or 0)


async def replace_watchlist(items: list[dict[str, Any]]) -> int:
    """整体替换关注列表（先清空再批量插入）。

    :param items: [{code, name, sort_order}] 列表。
    :returns: 写入条数。
    """
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(WatchlistModel))
        if items:
            session.add_all([WatchlistModel(**it) for it in items])
        await session.commit()
    return len(items)


# ---------------------------------------------------------------------------
# 分析报告（analysis_report）
# ---------------------------------------------------------------------------


async def upsert_analysis_reports(reports: Iterable[AnalysisReport]) -> int:
    """批量 upsert 分析报告，按 (code, trade_date) 覆盖。

    跳过 trade_date 为 None 的报告（拉 K 线失败的 report 不落库）。

    :param reports: AnalysisReport 列表。
    :returns: 写入条数。
    """
    rows: list[dict[str, Any]] = []
    for r in reports:
        if r.trade_date is None:
            continue
        rows.append(
            {
                "code": r.code,
                "trade_date": r.trade_date,
                "name": r.name,
                "close": r.close,
                "change_pct": r.change_pct,
                "trend": r.trend,
                "ok": r.ok,
                "payload": r.model_dump(mode="json"),
            }
        )
    if not rows:
        return 0

    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(AnalysisReportModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_report_code_date",
            set_={
                "name": stmt.excluded.name,
                "close": stmt.excluded.close,
                "change_pct": stmt.excluded.change_pct,
                "trend": stmt.excluded.trend,
                "ok": stmt.excluded.ok,
                "payload": stmt.excluded.payload,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


async def load_latest_reports(codes: list[str]) -> list[AnalysisReport]:
    """读取给定代码集合每只的最新一份报告。

    :param codes: 代码列表。
    :returns: AnalysisReport 列表。
    """
    if not codes:
        return []
    factory = get_session_factory()
    try:
        async with factory() as session:
            # 子查询：每个 code 的最大 trade_date
            sub = (
                select(
                    AnalysisReportModel.code,
                    func.max(AnalysisReportModel.trade_date).label("max_date"),
                )
                .where(AnalysisReportModel.code.in_(codes))
                .group_by(AnalysisReportModel.code)
                .subquery()
            )
            result = await session.execute(
                select(AnalysisReportModel)
                .join(
                    sub,
                    (AnalysisReportModel.code == sub.c.code)
                    & (AnalysisReportModel.trade_date == sub.c.max_date),
                )
            )
            return [
                AnalysisReport.model_validate(row.payload)
                for row in result.scalars().all()
            ]
    except Exception as e:  # noqa: BLE001
        logger.warning("load_latest_reports failed: %s", e)
        return []


async def load_reports_by_date(trade_date: date) -> list[AnalysisReport]:
    """按交易日加载全部报告。

    :param trade_date: 交易日。
    :returns: AnalysisReport 列表。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(AnalysisReportModel)
                .where(AnalysisReportModel.trade_date == trade_date)
                .order_by(AnalysisReportModel.code)
            )
            return [
                AnalysisReport.model_validate(row.payload)
                for row in result.scalars().all()
            ]
    except Exception as e:  # noqa: BLE001
        logger.warning("load_reports_by_date failed: %s", e)
        return []


async def load_report_history(code: str, limit: int = 30) -> list[AnalysisReport]:
    """加载某只标的的历史报告（按日期降序）。

    :param code: 证券代码。
    :param limit: 最大返回数。
    :returns: AnalysisReport 列表（最新在前）。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(AnalysisReportModel)
                .where(AnalysisReportModel.code == code)
                .order_by(AnalysisReportModel.trade_date.desc())
                .limit(limit)
            )
            return [
                AnalysisReport.model_validate(row.payload)
                for row in result.scalars().all()
            ]
    except Exception as e:  # noqa: BLE001
        logger.warning("load_report_history failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# K 线（kline）
# ---------------------------------------------------------------------------


async def upsert_klines(rows: Iterable[dict[str, Any]]) -> int:
    """批量 upsert K 线数据，按 (code, trade_date) 覆盖。

    :param rows: 字典迭代，需含 code / trade_date / open / close / high / low / volume。
    :returns: 写入条数。
    """
    rows = list(rows)
    if not rows:
        return 0

    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(KlineModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_kline_code_date",
            set_={
                "open": stmt.excluded.open,
                "close": stmt.excluded.close,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "volume": stmt.excluded.volume,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


async def load_kline(code: str, days: int = 120) -> Kline | None:
    """从 DB 读取某标的最近 N 根日 K 线，构造 Kline 对象。

    DB 无数据或不足时返回 None（调用方回退 Provider 拉取）。

    :param code: 证券代码。
    :param days: 返回的最近交易日数量。
    :returns: Kline 对象或 None。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(KlineModel)
                .where(KlineModel.code == code)
                .order_by(KlineModel.trade_date.desc())
                .limit(days)
            )
            models = list(result.scalars().all())
    except Exception as e:  # noqa: BLE001
        logger.warning("load_kline failed for %s: %s", code, e)
        return None

    if not models:
        return None

    # DB 是按日期降序取的，反转为升序（与 Provider.get_kline 一致）
    models.reverse()
    bars = [
        KlineBar(
            trade_date=m.trade_date,
            open=m.open,
            close=m.close,
            high=m.high,
            low=m.low,
            volume=m.volume,
        )
        for m in models
    ]
    return Kline(code=code, bars=bars)


async def get_kline_last_date(code: str) -> date | None:
    """查某 code 在 DB 中的最大交易日（增量同步起点）。

    :param code: 证券代码。
    :returns: 最大交易日，DB 无数据返回 None。
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(func.max(KlineModel.trade_date)).where(
                    KlineModel.code == code
                )
            )
            return result.scalar_one_or_none()
    except Exception as e:  # noqa: BLE001
        logger.warning("get_kline_last_date failed for %s: %s", code, e)
        return None


# ---------------------------------------------------------------------------
# 交易日历（market_calendar）
# ---------------------------------------------------------------------------


async def upsert_calendar(rows: Iterable[dict[str, Any]]) -> int:
    """批量 upsert 交易日历。

    :param rows: 字典迭代，需含 trade_date / is_open。
    :returns: 写入条数。
    """
    rows = list(rows)
    if not rows:
        return 0

    factory = get_session_factory()
    async with factory() as session:
        stmt = pg_insert(MarketCalendarModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date"], set_={"is_open": stmt.excluded.is_open}
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


async def is_trading_day(d: date | None = None) -> bool:
    """判断某天是否为交易日（DB market_calendar 有记录且 is_open=True）。

    DB 不可用或无记录时回退为星期判断（周一至五 True）。

    :param d: 日期，默认今天。
    :returns: 是否交易日。
    """
    if d is None:
        d = date.today()

    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(MarketCalendarModel.is_open).where(
                    MarketCalendarModel.trade_date == d
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return bool(row)
    except Exception as e:  # noqa: BLE001
        logger.warning("is_trading_day DB query failed: %s", e)

    # DB 无记录时回退为星期判断
    return d.weekday() < 5
