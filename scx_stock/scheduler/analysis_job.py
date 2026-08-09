"""
@description 每日支撑位分析任务：读取关注列表 → 拉取 K 线 → 计算分析 → AI 解读 → 发送邮件。

单只标的失败不阻断整体流程。可被 Scheduler 定时触发，也可被 API 手动触发。
"""

import logging
import time

from scx_stock.analysis.engine import analyze
from scx_stock.config.settings import get_settings
from scx_stock.llm.interpreter import interpret
from scx_stock.notify.email_sender import render_daily_report, send_email
from scx_stock.provider.akshare_provider import AkshareProvider
from scx_stock.schema.analysis import AnalysisReport

logger = logging.getLogger(__name__)


async def _analyze_one(
    provider: AkshareProvider, code: str, days: int, name: str = ""
) -> AnalysisReport:
    """分析单只标的：拉 K 线 → 计算支撑位 → AI 解读。

    任何步骤失败都返回 ok=False 的 report，不抛异常。

    :param provider: AkShare Provider 实例。
    :param code: 证券代码。
    :param days: K 线窗口。
    :param name: 标的名称（来自 DB 或调用方），回填到 report。
    :returns: AnalysisReport。
    """
    try:
        kline = await provider.get_kline(code, days=days)
    except Exception as e:  # noqa: BLE001
        logger.warning("拉取 K 线失败 %s: %s", code, e)
        return AnalysisReport(code=code, name=name, ok=False, error=f"拉取 K 线失败: {e}")

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
        from scx_stock.storage import repo

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
    :param codes: 指定分析的代码列表；为 None 时读 SCX_WATCHLIST 配置。
    :returns: {"analyzed": N, "success": N, "failed": N, "sent": bool, "reports": [...], "elapsed": 秒}。
    """
    s = get_settings()
    target_codes = codes if codes is not None else s.watchlist_codes()
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

    sent = False
    if not dry_run:
        recipients = s.notify_email_list()
        if recipients and success > 0:
            html = render_daily_report(reports)
            sent = await send_email(recipients, html)
        elif not recipients:
            logger.warning("未配置收件人（SCX_NOTIFY_EMAILS），跳过邮件发送")

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

    :returns: 分析结果汇总。
    """
    return await run_daily_analysis(dry_run=False)
