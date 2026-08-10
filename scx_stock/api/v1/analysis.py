"""
@description 支撑位分析 API：手动触发分析 + 查看历史报告。
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query

from scx_stock.middleware.rate_limit import ai_rate_limit
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.scheduler.analysis_job import run_daily_analysis
from scx_stock.storage import repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["AI分析"])


@router.post("/run", response_model=ApiResponse, summary="手动触发支撑位分析")
async def run_analysis(
    dry_run: bool = Query(False, description="True 只分析不发邮件，返回完整结果"),
    codes: str | None = Query(
        None,
        description="指定分析的代码列表（逗号分隔）；不传则读 DB 关注列表",
    ),
    _=Depends(ai_rate_limit()),
) -> dict[str, object]:
    """手动触发每日支撑位分析任务。

    可通过 ``codes`` 参数传入代码列表（逗号分隔），未传则读 DB watchlist 表。
    分析结果会落库（analysis_report 表），后续可查历史。

    单只标的数据源/AI 失败不影响其他标的，返回结果中标记 ok=False。

    :param dry_run: 是否只分析不发邮件。
    :param codes: 逗号分隔的代码列表（可选）。
    :returns: 统一响应，data 含 analyzed/success/failed/sent/reports。
    """
    code_list = (
        [c.strip() for c in codes.split(",") if c.strip()] if codes else None
    )
    result = await run_daily_analysis(dry_run=dry_run, codes=code_list)
    return ok(result)


@router.get("/latest", response_model=ApiResponse, summary="获取最新分析报告")
async def get_latest_reports(
    codes: str | None = Query(
        None,
        description="指定代码列表（逗号分隔）；不传则返回关注列表的最新报告",
    ),
) -> dict[str, object]:
    """获取每只标的的最新一份分析报告（从 DB 读取，不触发重算）。

    :param codes: 逗号分隔的代码列表（可选）。
    :returns: 统一响应，data 为 AnalysisReport 列表。
    """
    if codes:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        code_list = await repo.list_watchlist_codes()

    reports = await repo.load_latest_reports(code_list)
    return ok([r.model_dump(mode="json") for r in reports])


@router.get("/history", response_model=ApiResponse, summary="获取标的历史分析报告")
async def get_report_history(
    code: str = Query(..., description="证券代码"),
    limit: int = Query(30, ge=1, le=365, description="最大返回数"),
) -> dict[str, object]:
    """获取某只标的的历史分析报告（按日期降序）。

    :param code: 证券代码。
    :param limit: 最大返回数。
    :returns: 统一响应，data 为 AnalysisReport 列表。
    """
    reports = await repo.load_report_history(code, limit=limit)
    return ok([r.model_dump(mode="json") for r in reports])


@router.get("/report/{trade_date}", response_model=ApiResponse, summary="按日期获取分析报告")
async def get_reports_by_date(trade_date: date) -> dict[str, object]:
    """获取某交易日的全部分析报告。

    :param trade_date: 交易日（YYYY-MM-DD）。
    :returns: 统一响应，data 为 AnalysisReport 列表。
    """
    reports = await repo.load_reports_by_date(trade_date)
    return ok([r.model_dump(mode="json") for r in reports])
