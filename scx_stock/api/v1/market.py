"""
@description 大盘指数 API 路由。
"""

from fastapi import APIRouter, Depends, Query

from scx_stock.api.deps import get_index_service
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.service.index_service import IndexService

router = APIRouter(prefix="/market", tags=["大盘"])


@router.get("/index", response_model=ApiResponse, summary="主要大盘指数")
async def list_major_indexes(
    service: IndexService = Depends(get_index_service),
) -> dict[str, object]:
    """获取主要大盘指数（上证/深证/创业板/科创50/北证50/沪深300 等）。

    :param service: IndexService。
    :returns: 统一响应，data 为 IndexQuote 列表。
    """
    indexes = await service.list_major_indexes()
    return ok([i.model_dump() for i in indexes])


@router.get("/index/all", response_model=ApiResponse, summary="全部指数（按分组）")
async def list_indexes(
    group: str = Query(
        "沪深重要指数",
        description="指数分组：沪深重要指数/上证系列指数/深证系列指数/指数成份/中证系列指数",
    ),
    service: IndexService = Depends(get_index_service),
) -> dict[str, object]:
    """获取指定分组的全部指数。

    :param group: 指数分组。
    :param service: IndexService。
    :returns: 统一响应，data 为 IndexQuote 列表。
    """
    indexes = await service.list_indexes(group)
    return ok([i.model_dump() for i in indexes])
