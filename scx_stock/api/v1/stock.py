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
