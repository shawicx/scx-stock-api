"""
@description Scheduler 同步任务：拉取股票/ETF 列表写入 DB，重建搜索索引。
"""

import logging

from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.search.index import get_index
from scx_stock.search.pinyin import make_pinyin_for_search
from scx_stock.storage import repo

logger = logging.getLogger(__name__)


def _classify_market(code: str) -> str:
    """按代码前缀识别市场。

    :param code: 股票代码。
    :returns: 市场名。
    """
    if not code:
        return "未知"
    head = code[0]
    if head == "6":
        return "上证"
    if head in ("0", "3"):
        return "深证"
    if head in ("8", "4"):
        return "北交所"
    return "其他"


def _to_rows(items, default_type: str) -> list[dict]:
    """StockInfo 列表转 DB 行字典。

    :param items: StockInfo 可迭代对象。
    :param default_type: stock / etf。
    :returns: dict 列表。
    """
    # 与 StockModel.pinyin 的 VARCHAR(128) 对齐，防超长基金名打爆整批写入
    pinyin_max = 128
    rows = []
    for it in items:
        pinyin = it.pinyin or make_pinyin_for_search(it.name)
        rows.append(
            {
                "code": it.code,
                "name": it.name,
                "market": it.market or _classify_market(it.code),
                "pinyin": pinyin[:pinyin_max],
                "type": it.type or default_type,
            }
        )
    return rows


async def sync_stock_list() -> dict[str, int]:
    """同步 A 股全量股票列表到 DB。

    :returns: {"stock_count": N}。
    """
    import time

    provider = AkshareProvider()
    t0 = time.time()
    try:
        items = await provider.list_stocks()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "sync_stock_list fetch failed in %.1fs: %s: %s",
            time.time() - t0, type(e).__name__, str(e)[:200],
        )
        return {"stock_count": 0}

    logger.info(
        "sync_stock_list fetched %d stocks in %.1fs, writing to DB",
        len(items), time.time() - t0,
    )
    rows = _to_rows(items, "stock")
    try:
        written = await repo.upsert_stocks(rows)
    except Exception as e:  # noqa: BLE001
        logger.exception("sync_stock_list db write failed: %s", e)
        return {"stock_count": 0}

    logger.info("sync_stock_list done: %d stocks in %.1fs", written, time.time() - t0)
    return {"stock_count": written}


async def sync_etf_list() -> dict[str, int]:
    """同步全量 ETF 列表到 DB。

    :returns: {"etf_count": N}。
    """
    import time

    provider = AkshareProvider()
    t0 = time.time()
    try:
        items = await provider.list_etfs()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "sync_etf_list fetch failed in %.1fs: %s: %s",
            time.time() - t0, type(e).__name__, str(e)[:200],
        )
        return {"etf_count": 0}

    logger.info(
        "sync_etf_list fetched %d etfs in %.1fs, writing to DB",
        len(items), time.time() - t0,
    )
    rows = _to_rows(items, "etf")
    try:
        written = await repo.upsert_stocks(rows)
    except Exception as e:  # noqa: BLE001
        logger.exception("sync_etf_list db write failed: %s", e)
        return {"etf_count": 0}

    logger.info("sync_etf_list done: %d etfs in %.1fs", written, time.time() - t0)
    return {"etf_count": written}


async def rebuild_search_index() -> dict[str, int]:
    """从 DB 全量加载，重建内存搜索索引。

    :returns: {"index_size": N}。
    """
    from scx_stock.schema.stock import StockInfo

    models = await repo.load_all_stocks()
    items = [
        StockInfo(
            code=m.code,
            name=m.name,
            market=m.market,
            pinyin=m.pinyin,
            type=m.type,
        )
        for m in models
    ]
    size = get_index().rebuild(items)
    logger.info("rebuild_search_index done: %d entries", size)
    return {"index_size": size}


async def sync_stock_industries() -> dict[str, int]:
    """从行业板块成分股反查，构建 code → industry 映射并写入 DB。

    流程：获取全部行业板块 → 逐个拉成分股 → 提取 code↔industry 行。
    单个板块失败不影响整体，容错跳过。

    :returns: {"industry_count": N}。
    """
    import time

    import akshare as ak

    provider = AkshareProvider()
    t0 = time.time()

    # 1. 获取全部行业板块
    try:
        sectors = await provider.list_sectors()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "sync_stock_industries fetch sectors failed in %.1fs: %s: %s",
            time.time() - t0, type(e).__name__, str(e)[:200],
        )
        return {"industry_count": 0}

    # 2. 逐板块拉成分股，提取 code → 行业映射
    rows: list[dict[str, str]] = []
    for sector in sectors:
        try:
            # 传入 label 供新浪源 fallback 使用
            constituents = await provider.get_sector_constituents(
                sector.name, sector_label=sector.label or sector.code
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("sync_stock_industries skip sector %s: %s", sector.name, e)
            continue
        for c in constituents:
            code = c.get("code", "").strip()
            if code:
                rows.append({"code": code, "industry": sector.name})

    if not rows:
        logger.warning("sync_stock_industries got empty rows in %.1fs", time.time() - t0)
        return {"industry_count": 0}

    # 3. 写入 DB
    try:
        written = await repo.upsert_stock_industries(rows)
    except Exception as e:  # noqa: BLE001
        logger.exception("sync_stock_industries db write failed: %s", e)
        return {"industry_count": 0}

    logger.info(
        "sync_stock_industries done: %d mappings in %.1fs",
        written, time.time() - t0,
    )
    return {"industry_count": written}


async def sync_kline(codes: list[str] | None = None) -> dict[str, int]:
    """增量同步关注列表的日 K 线到 DB。

    codes 为 None 时读 DB watchlist + .env 回退。
    对每个 code：查 DB 最大 trade_date → 增量拉取 → upsert 落库。
    若 DB 无此 code 数据，拉最近 120 日全量初始化。

    :param codes: 代码列表，None 时读关注列表。
    :returns: {"synced": N, "failed": N}。
    """
    import time

    from scx_stock.config.settings import get_settings

    t0 = time.time()

    # 获取目标代码列表
    if codes is None:
        codes = await repo.list_watchlist_codes()
        if not codes:
            s = get_settings()
            codes = s.watchlist_codes()

    if not codes:
        logger.warning("sync_kline: 关注列表为空，跳过")
        return {"synced": 0, "failed": 0}

    provider = AkshareProvider()
    synced = 0
    failed = 0

    for code in codes:
        try:
            # 查 DB 最大交易日，决定是增量还是全量
            last_date = await repo.get_kline_last_date(code)
            if last_date:
                # 增量：从 last_date 开始拉
                kline = await provider.get_kline(code, days=0)  # days=0 不截断
                # 过滤出 last_date 之后的数据
                new_bars = [b for b in kline.bars if b.trade_date > last_date]
            else:
                # 全量初始化：拉最近 120 日
                kline = await provider.get_kline(code, days=120)
                new_bars = kline.bars

            if not new_bars:
                logger.debug("sync_kline %s: 无新数据", code)
                synced += 1
                continue

            rows = [
                {
                    "code": code,
                    "trade_date": b.trade_date,
                    "open": b.open,
                    "close": b.close,
                    "high": b.high,
                    "low": b.low,
                    "volume": b.volume,
                }
                for b in new_bars
            ]
            written = await repo.upsert_klines(rows)
            logger.info("sync_kline %s: 写入 %d 根（last_date=%s）", code, written, last_date)
            synced += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("sync_kline %s failed: %s", code, e)
            failed += 1

    logger.info(
        "sync_kline done: %d synced, %d failed in %.1fs",
        synced, failed, time.time() - t0,
    )
    return {"synced": synced, "failed": failed}


async def sync_market_calendar() -> dict[str, int]:
    """同步交易日历到 DB（新浪 tool_trade_date_hist_sina）。

    数据源返回 1990-2026 全量交易日（~8797 行），upsert 到 market_calendar 表。

    :returns: {"calendar_count": N}。
    """
    import time

    import akshare as ak

    t0 = time.time()
    try:
        df = await AkshareProvider()._run(ak.tool_trade_date_hist_sina)
    except Exception as e:  # noqa: BLE001
        logger.warning("sync_market_calendar fetch failed: %s", e)
        return {"calendar_count": 0}

    if df is None or df.empty:
        return {"calendar_count": 0}

    rows = [
        {"trade_date": d, "is_open": True}
        for d in df["trade_date"]
    ]
    try:
        written = await repo.upsert_calendar(rows)
    except Exception as e:  # noqa: BLE001
        logger.exception("sync_market_calendar db write failed: %s", e)
        return {"calendar_count": 0}

    logger.info(
        "sync_market_calendar done: %d trade dates in %.1fs",
        written, time.time() - t0,
    )
    return {"calendar_count": written}


async def sync_all() -> dict[str, int]:
    """串行执行：股票列表 → ETF 列表 → 行业映射 → 重建索引。

    :returns: 汇总计数。
    """
    r1 = await sync_stock_list()
    r2 = await sync_etf_list()
    r3 = await sync_stock_industries()
    r4 = await rebuild_search_index()
    return {**r1, **r2, **r3, **r4}
