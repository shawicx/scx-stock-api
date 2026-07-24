"""
@description 搜索 API 路由。
"""

from fastapi import APIRouter, Depends, Query

from scx_stock.api.deps import get_search_service
from scx_stock.service.search_service import SearchService

router = APIRouter(prefix="/search", tags=["搜索"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词：代码/简称/拼音"),
    limit: int = Query(20, ge=1, le=100),
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    """搜索股票 / ETF。

    :param q: 关键词。
    :param limit: 最大返回数。
    :param service: SearchService。
    :returns: 搜索结果。
    """
    results = await service.search(q, limit=limit)
    return {"code": 0, "data": results}


@router.get("/index-size")
async def index_size(
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    """返回当前内存索引条目数（运维用）。

    :param service: SearchService。
    :returns: 索引大小。
    """
    size = await service.index_size()
    return {"code": 0, "data": {"size": size}}
