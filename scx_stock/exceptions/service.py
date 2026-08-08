"""
@description Service 层异常定义。
"""


class ServiceError(Exception):
    """业务逻辑异常基类。"""


class NotFoundError(ServiceError):
    """资源不存在（如股票代码不存在）。"""


class ValidationError(ServiceError):
    """业务校验失败。"""


class RateLimitExceededError(ServiceError):
    """请求超出限流阈值。

    :param message: 错误描述。
    :param retry_after: 建议客户端等待重试的秒数（写入 Retry-After 响应头）。
    """

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after
