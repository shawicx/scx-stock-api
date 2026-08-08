"""
@description 个股 API 路由，参数校验 → 调 Service → 返回统一格式 JSON。
"""

import re

from fastapi import APIRouter, Depends, Query

from scx_stock.api.deps import get_stock_service
from scx_stock.exceptions.service import ValidationError
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.service.stock_service import StockService

router = APIRouter(prefix="/stock", tags=["个股"])

# A 股代码规则：6 位数字，首位 0/3/6/8；北交所 5-6 位
_CODE_RE = re.compile(r"^[0368]\d{4,5}$")


@router.get("/list", response_model=ApiResponse, summary="获取股票/ETF行情列表")
async def list_stocks(
    market: str = Query(
        "全部",
        pattern="^(上证|深证|创业板|科创板|北交所|全部)$",
        description="市场板块筛选",
    ),
    type: str = Query(
        "stock",
        pattern="^(stock|etf|all)$",
        description="证券类型：stock/etf/all",
    ),
    sort_by: str = Query(
        "change_pct",
        pattern="^(change_pct|amount|turnover_rate|main_net_inflow)$",
        description="排序字段",
    ),
    descending: bool = Query(True, description="是否降序"),
    page: int = Query(1, ge=1, description="页码（从 1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（1~100）"),
    service: StockService = Depends(get_stock_service),
) -> dict[str, object]:
    """获取股票/ETF 实时行情列表（含涨跌、成交、换手等）。

    数据源实时拉取 + Redis 分钟级缓存，支持市场细分筛选、排序、内存分页。

    :param market: 市场板块。
    :param type: 证券类型。
    :param sort_by: 排序字段。
    :param descending: 是否降序。
    :param page: 页码。
    :param page_size: 每页条数。
    :param service: StockService。
    :returns: 统一响应，data 为 {items, total, page, page_size}。
    """
    items, total = await service.list_stocks(
        market=market,
        type_=type,
        sort_by=sort_by,
        descending=descending,
        page=page,
        page_size=page_size,
    )
    return ok(
        {
            "items": [i.model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{code}", response_model=ApiResponse, summary="获取个股详情")
async def get_stock_detail(
    code: str,
    service: StockService = Depends(get_stock_service),
) -> dict[str, object]:
    """获取个股详情（基础信息 + 实时行情）。

    :param code: 股票代码。
    :param service: StockService 实例（依赖注入）。
    :returns: 统一响应，data 为聚合详情。
    :raises ValidationError: 代码格式错误。
    """
    code = code.strip()
    if not _CODE_RE.match(code):
        raise ValidationError(f"无效的股票代码: {code}")

    detail = await service.get_detail(code)
    return ok(detail.to_dict())
