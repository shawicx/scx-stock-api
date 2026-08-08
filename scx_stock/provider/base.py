"""
@description Provider 基类，强制同步库走线程池，对外暴露 async。

附带代理兼容处理：部分代理环境（Clash MITM / TUN fake-ip）对东方财富等国内
数据源的 HTTPS 握手有干扰（SSL record layer failure）。通过 monkey-patch
requests.Session，让国内数据源域名绕过系统代理直连。
"""

from typing import Any, Callable

import requests
from anyio import to_thread

# 需要绕过代理直连的国内数据源域名
_DIRECT_DOMAINS = (
    "push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "7.push2.eastmoney.com",
    "17.push2.eastmoney.com",
    "push2delay.eastmoney.com",
    "datacenter.eastmoney.com",
    "data.eastmoney.com",
    "hq.sinajs.cn",
    "vip.stock.finance.sina.com.cn",
    "qt.gtimg.cn",
    "web.ifzq.gtimg.cn",
    "money.finance.sina.com.cn",
)

_original_session_request = requests.Session.request


def _patched_session_request(
    self: Any, method: str, url: str, *args: Any, **kwargs: Any
):
    """requests.Session.request 补丁：对国内数据源强制绕过代理直连。

    AkShare 内部创建独立 requests.Session 发请求，会继承系统代理设置。
    代理对国内 HTTPS 接口做 MITM 会导致 SSL record layer failure。
    此补丁检测 URL 域名，对国内数据源设置 proxies={} 强制直连。

    :param self: Session 实例。
    :param method: HTTP 方法。
    :param url: 请求 URL。
    :returns: requests.Response。
    """
    if any(d in url for d in _DIRECT_DOMAINS):
        kwargs.setdefault("proxies", {"http": None, "https": None})
    return _original_session_request(self, method, url, *args, **kwargs)


requests.Session.request = _patched_session_request  # type: ignore[method-assign]


class SyncProviderBase:
    """同步数据源基类。

    AkShare 等同步库若直接在 async 路径调用会阻塞事件循环，
    子类统一通过 _run 把同步函数推入线程池执行。
    """

    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """在线程池中执行同步函数。

        :param func: 同步可调用对象。
        :param args: 位置参数。
        :param kwargs: 关键字参数。
        :returns: 函数返回值。
        """
        return await to_thread.run_sync(lambda: func(*args, **kwargs))
