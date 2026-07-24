"""
@description 公共响应模型，统一成功/错误响应格式，供前端联调依赖 OpenAPI 契约。
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包装。

    :param code: 业务码，0 表示成功，非 0 表示业务错误。
    :param message: 描述信息，成功为 "ok"。
    :param data: 业务数据。
    """

    code: int = Field(0, description="业务码：0 成功，非 0 错误")
    message: str = Field("ok", description="描述信息")
    data: T | None = Field(None, description="业务数据")


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """构造成功响应字典。

    :param data: 业务数据。
    :param message: 描述信息。
    :returns: ``{"code":0, "message":..., "data":...}``。

    :example ok({"price": 1800})
    {"code": 0, "message": "ok", "data": {"price": 1800}}
    """
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """构造失败响应字典。

    :param code: 非零业务码。
    :param message: 错误描述。
    :param data: 可选附加数据。
    :returns: ``{"code":..., "message":..., "data":...}``。

    :example fail(400, "参数错误")
    {"code": 400, "message": "参数错误", "data": None}
    """
    return {"code": code, "message": message, "data": data}


class PageData(BaseModel, Generic[T]):
    """分页数据包装。

    :param items: 当前页条目。
    :param total: 总条数。
    :param page: 当前页码（从 1 起）。
    :param page_size: 每页大小。
    """

    items: list[T]
    total: int
    page: int
    page_size: int


class HealthStatus(BaseModel):
    """健康检查响应。

    :param status: 总体状态 ok/degraded。
    :param app: 应用名。
    :param version: 版本号。
    :param checks: 各组件状态。
    """

    status: str
    app: str
    version: str
    checks: dict[str, str]
