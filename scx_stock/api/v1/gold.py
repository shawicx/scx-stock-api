"""
@description 黄金行情 API 路由。
"""

from fastapi import APIRouter, Depends

from scx_stock.api.deps import get_gold_service
from scx_stock.schema.common import ApiResponse, ok
from scx_stock.schema.gold import GoldQuote
from scx_stock.service.gold_service import GoldService

router = APIRouter(prefix="/market/gold", tags=["黄金行情"])


@router.get("", response_model=ApiResponse, summary="获取黄金品种实时行情")
async def list_gold_quotes(
    service: GoldService = Depends(get_gold_service),
) -> dict[str, object]:
    """返回国内主要黄金品种的实时行情。

    包含：沪金主连 AU0（上期所期货）、上金所现货 Au99.99、纽约金跟踪 NYAuTN06。
    全部人民币计价（CNY/克）。数据有 120 秒缓存。

    :param service: GoldService（依赖注入）。
    :returns: 统一响应，data 为 GoldQuote 列表。
    """
    quotes = await service.list_gold_quotes()
    return ok([q.model_dump() for q in quotes])
