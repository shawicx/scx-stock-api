"""
@description Provider 层异常定义。
"""


class ProviderError(Exception):
    """数据源访问异常（超时、限流、源不可用等）。"""


class ProviderUnavailableError(ProviderError):
    """数据源不可用。"""


class ProviderTimeoutError(ProviderError):
    """数据源访问超时。"""


class ProviderRateLimitError(ProviderError):
    """数据源触发限流。"""
