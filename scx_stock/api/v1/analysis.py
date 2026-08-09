"""
@description 支撑位分析 API 路由：手动触发分析（dry_run 或发送邮件）。
"""

import logging

from fastapi import APIRouter, Depends, Query

from scx_stock.middleware.rate_limit import ai_rate_limit
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.scheduler.analysis_job import run_daily_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["AI分析"])


@router.post("/run", response_model=ApiResponse, summary="手动触发支撑位分析")
async def run_analysis(
    dry_run: bool = Query(False, description="True 只分析不发邮件，返回完整结果"),
    codes: str | None = Query(
        None,
        description="指定分析的代码列表（逗号分隔）；不传则读后端 SCX_WATCHLIST 配置",
    ),
    _=Depends(ai_rate_limit()),
) -> dict[str, object]:
    """手动触发每日支撑位分析任务。

    可通过 ``codes`` 参数传入前端关注列表（逗号分隔代码），未传则读后端配置。
    逐标的拉取 K 线 → 计算支撑位 → AI 解读。

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
