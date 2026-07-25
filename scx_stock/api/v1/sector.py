"""
@description 板块 API 路由。
"""

from fastapi import APIRouter, Depends, Query

from scx_stock.api.deps import get_sector_service
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.service.sector_service import SectorService

router = APIRouter(prefix="/sector", tags=["板块"])


@router.get("/list", response_model=ApiResponse, summary="板块涨跌排行")
async def list_sectors(
    sort_by: str = Query(
        "change_pct", description="排序字段：change_pct/turnover_rate/total_market_cap"
    ),
    descending: bool = Query(True, description="是否降序"),
    limit: int = Query(50, ge=1, le=200, description="最大返回数"),
    service: SectorService = Depends(get_sector_service),
) -> dict[str, object]:
    """获取行业板块涨跌排行。

    :param sort_by: 排序字段。
    :param descending: 是否降序。
    :param limit: 最大返回数。
    :param service: SectorService。
    :returns: 统一响应，data 为 SectorQuote 列表。
    """
    sectors = await service.list_sectors(
        sort_by=sort_by, descending=descending, limit=limit
    )
    return ok([s.model_dump() for s in sectors])


@router.get("/{name}", response_model=ApiResponse, summary="板块详情")
async def get_sector_detail(
    name: str,
    service: SectorService = Depends(get_sector_service),
) -> dict[str, object]:
    """获取板块详情（行情 + 成分股）。

    :param name: 板块名称（如 "小金属"）。
    :param service: SectorService。
    :returns: 统一响应，data 为 SectorDetail。
    """
    detail = await service.get_sector_detail(name)
    return ok(detail.model_dump())
