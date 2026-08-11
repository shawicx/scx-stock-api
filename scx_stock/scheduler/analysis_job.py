"""
@description 每日支撑位分析任务：读取关注列表 → 拉取 K 线 → 计算分析 → AI 解读 → 发送邮件。

单只标的失败不阻断整体流程。可被 Scheduler 定时触发，也可被 API 手动触发。
"""

import logging
import time

from scx_stock.analysis.engine import analyze
from scx_stock.config.settings import get_settings
from scx_stock.config.dynamic import get_dynamic_settings
from scx_stock.llm.interpreter import interpret
from scx_stock.notify.email_sender import render_daily_report, send_email
from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.storage import repo
from scx_stock.schema.analysis import AnalysisReport

logger = logging.getLogger(__name__)


async def _analyze_one(
    provider: AkshareProvider, code: str, days: int, name: str = ""
) -> AnalysisReport:
    """分析单只标的：拉 K 线 → 计算支撑位 → AI 解读。

    K 线优先从 DB 读取（sync_kline 定时任务预置），DB 不足时回退 Provider 拉取
    并顺带落库。任何步骤失败都返回 ok=False 的 report，不抛异常。

    :param provider: AkShare Provider 实例。
    :param code: 证券代码。
    :param days: K 线窗口。
    :param name: 标的名称（来自 DB 或调用方），回填到 report。
    :returns: AnalysisReport。
    """
    # 1. 优先从 DB 读 K 线
    kline = await repo.load_kline(code, days)
    used_db = kline is not None and len(kline.bars) >= 30

    if not used_db:
        # 2. DB 不足时回退 Provider 拉取
        try:
            kline = await provider.get_kline(code, days=days)
        except Exception as e:  # noqa: BLE001
            logger.warning("拉取 K 线失败 %s: %s", code, e)
            return AnalysisReport(code=code, name=name, ok=False, error=f"拉取 K 线失败: {e}")

        # 3. 顺带落库（容错，不阻断分析）
        try:
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
                for b in kline.bars
            ]
            await repo.upsert_klines(rows)
            logger.info("K 线回填 DB %s: %d 根", code, len(rows))
        except Exception as e:  # noqa: BLE001
            logger.debug("K 线回填 DB 失败 %s: %s", code, e)

    kline.name = name  # 透传名称到分析结果
    report = analyze(kline)
    if not report.ok:
        return report

    report = await interpret(report)
    return report


async def _resolve_names(codes: list[str]) -> dict[str, str]:
    """从 DB 查询代码→名称映射，DB 不可用时返回空字典。

    :param codes: 代码列表。
    :returns: {code: name} 字典。
    """
    try:
        models = await repo.load_all_stocks()
        return {m.code: m.name for m in models if m.code in codes}
    except Exception as e:  # noqa: BLE001
        logger.warning("查询标的名称失败，名称将为空: %s", e)
        return {}


async def run_daily_analysis(
    dry_run: bool = False, codes: list[str] | None = None
) -> dict:
    """执行每日分析任务，可选发送邮件。

    :param dry_run: True 只分析不发邮件，返回结果列表。
    :param codes: 指定分析的代码列表；为 None 时优先读 DB watchlist，回退 .env。
    :returns: {"analyzed": N, "success": N, "failed": N, "sent": bool, "reports": [...], "elapsed": 秒}。
    """
    s = get_settings()
    if codes is not None:
        target_codes = codes
    else:
        # 定时任务入口：优先读 DB watchlist，为空则回退 .env SCX_WATCHLIST
        target_codes = await repo.list_watchlist_codes()
        if not target_codes:
            target_codes = s.watchlist_codes()

    if not target_codes:
        logger.warning("关注列表为空，跳过分析")
        return {"analyzed": 0, "success": 0, "failed": 0, "sent": False, "reports": [], "elapsed": 0}

    t0 = time.time()
    provider = AkshareProvider()
    days = s.analysis_kline_days
    name_map = await _resolve_names(target_codes)

    reports: list[AnalysisReport] = []
    for code in target_codes:
        name = name_map.get(code, "")
        report = await _analyze_one(provider, code, days, name=name)
        reports.append(report)
        status = "ok" if report.ok else "FAIL"
        logger.info("分析 %s %s: close=%s trend=%s", code, status, report.close, report.trend)

    success = sum(1 for r in reports if r.ok)
    failed = len(reports) - success
    elapsed = round(time.time() - t0, 1)

    # 分析结果落库（dry_run 也落库，仅不发邮件）
    try:
        saved = await repo.upsert_analysis_reports(reports)
        logger.info("分析报告落库 %d 条", saved)
    except Exception as e:  # noqa: BLE001
        logger.warning("分析报告落库失败: %s", e)

    sent = False
    if not dry_run:
        # 收件人优先读 DB（前端配置），回退 .env
        cfg = await get_dynamic_settings(["notify_emails"])
        notify_raw = cfg.get("notify_emails") or ""
        recipients = [e.strip() for e in notify_raw.split(",") if e.strip()]
        if recipients and success > 0:
            html = await render_daily_report(reports)
            sent, send_error = await send_email(recipients, html)
            if not sent and send_error:
                logger.warning("邮件发送失败: %s", send_error)
        elif not recipients:
            logger.warning("未配置收件人，跳过邮件发送")

    logger.info(
        "每日分析完成: 共 %d 只，成功 %d，失败 %d，耗时 %.1fs，邮件=%s",
        len(reports), success, failed, elapsed, sent,
    )
    return {
        "analyzed": len(reports),
        "success": success,
        "failed": failed,
        "sent": sent,
        "reports": [r.model_dump(mode="json") for r in reports],
        "elapsed": elapsed,
    }


async def daily_analysis_job() -> dict:
    """Scheduler 定时任务入口（非 dry_run，发送邮件）。

    非交易日（周末/节假日）自动跳过，避免无意义的分析+邮件。

    :returns: 分析结果汇总。
    """
    # 交易日历门控：非交易日跳过
    if not await repo.is_trading_day():
        logger.info("今日非交易日，跳过分析")
        return {"analyzed": 0, "success": 0, "failed": 0, "sent": False, "skipped": True}

    return await run_daily_analysis(dry_run=False)
