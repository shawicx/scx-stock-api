"""
@description 全局异常处理器，把 Service / Provider 异常统一映射为 {code, message, data} JSON。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from scx_stock.exceptions.provider import ProviderError
from scx_stock.exceptions.service import NotFoundError, ServiceError, ValidationError


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。

    所有错误统一返回 ``{"code": <非零>, "message": <描述>, "data": null}``，
    HTTP 状态码同步保持语义（400/404/502/500），便于前端按需选择判断方式。

    :param app: FastAPI 应用。
    """

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"code": 40401, "message": str(exc), "data": None},
        )

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"code": 40001, "message": str(exc), "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def _req_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """把 FastAPI 参数校验错误统一成同一格式，方便前端展示。

        :param exc: 校验异常（含 errors() 详情）。
        """
        return JSONResponse(
            status_code=422,
            content={
                "code": 42201,
                "message": "请求参数校验失败",
                "data": exc.errors(),
            },
        )

    @app.exception_handler(ProviderError)
    async def _provider(_: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"code": 50201, "message": f"数据源异常: {exc}", "data": None},
        )

    @app.exception_handler(ServiceError)
    async def _service(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"code": 50001, "message": str(exc), "data": None},
        )
