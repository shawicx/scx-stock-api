"""
@description Service 层异常定义。
"""


class ServiceError(Exception):
    """业务逻辑异常基类。"""


class NotFoundError(ServiceError):
    """资源不存在（如股票代码不存在）。"""


class ValidationError(ServiceError):
    """业务校验失败。"""
