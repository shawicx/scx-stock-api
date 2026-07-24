"""
@description 搜索 API 路由。
"""

from fastapi import APIRouter, Depends, Query

from scx_stock.api.deps import get_search_service
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.service.search_service import SearchService

router = APIRouter(prefix="/search", tags=["搜索"])


@router.get("", response_model=ApiResponse, summary="搜索股票/ETF/指数")
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词：代码/简称/拼音"),
    limit: int = Query(20, ge=1, le=100, description="最大返回条数"),
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    """搜索股票 / ETF。

    :param q: 关键词。
    :param limit: 最大返回数。
    :param service: SearchService。
    :returns: 统一响应，data 为结果列表。
    """
    results = await service.search(q, limit=limit)
    return ok(results)


@router.get("/index-size", response_model=ApiResponse, summary="搜索索引大小")
async def index_size(
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    """返回当前内存索引条目数（运维用）。

    :param service: SearchService。
    :returns: 统一响应，data 含 size 字段。
    """
    size = await service.index_size()
    return ok({"size": size})
