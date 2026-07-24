"""
@description 全局异常处理器，把 Service / Provider 异常统一映射为 JSON 响应。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scx_stock.exceptions.provider import ProviderError
from scx_stock.exceptions.service import NotFoundError, ServiceError, ValidationError


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。

    :param app: FastAPI 应用。
    """

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": 404, "message": str(exc)})

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"code": 400, "message": str(exc)})

    @app.exception_handler(ProviderError)
    async def _provider(_: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"code": 502, "message": f"数据源异常: {exc}"}
        )

    @app.exception_handler(ServiceError)
    async def _service(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"code": 500, "message": str(exc)})
