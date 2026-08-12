"""
@description Provider 基类，强制同步库走线程池，对外暴露 async。

附带数据源兼容处理（monkey-patch requests.Session）：
1. 注入浏览器 User-Agent：东方财富等数据源会拒绝无 UA 的请求（RemoteDisconnected），
   AkShare 内部 requests.Session 不设 UA，需在 session 级别统一注入。
2. 国内数据源绕过系统代理：部分代理环境对国内 HTTPS 做 MITM 导致 SSL 失败。
3. 东方财富域名缩短超时：AkShare 默认 timeout=15s + 重试3次（最坏 ~50s），
   对已知的反爬域名强制 5 秒超时，加速 fallback 切换。
"""

from typing import Any, Callable

import requests
from anyio import to_thread

# 浏览器 User-Agent，伪装正常浏览器请求
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 需要绕过代理直连的国内数据源域名
_DIRECT_DOMAINS = (
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
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
    # 同花顺（fund.10jqka.com.cn / stockpage.10jqka.com.cn）
    "10jqka.com.cn",
    # 上金所（黄金现货）
    "sge.com.cn",
    # 新浪基金
    "finance.sina.com.cn",
)

# 东方财富域名（反爬高风险，需缩短超时加速 fallback）
_EM_DOMAINS = (
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
    "82.push2.eastmoney.com",
    "7.push2.eastmoney.com",
    "17.push2.eastmoney.com",
    "push2delay.eastmoney.com",
    "datacenter.eastmoney.com",
    "data.eastmoney.com",
)

# 东方财富域名强制超时秒数（覆盖 AkShare 默认的 15 秒）
_EM_TIMEOUT = 5

_original_session_request = requests.Session.request


def _patched_session_request(
    self: Any, method: str, url: str, *args: Any, **kwargs: Any
):
    """requests.Session.request 补丁：注入 UA + 国内源绕过代理 + 东方财富缩短超时。

    AkShare 内部创建独立 requests.Session 发请求，默认无 User-Agent 且
    继承系统代理。此补丁：
    - 统一注入浏览器 User-Agent（避免被东方财富反爬拒绝）
    - 对国内数据源域名设置 proxies={} 强制直连（避免代理 SSL 干扰）
    - 对东方财富域名强制 timeout=5s（加速 fallback，避免 3 次重试各 15 秒）

    :param self: Session 实例。
    :param method: HTTP 方法。
    :param url: 请求 URL。
    :returns: requests.Response。
    """
    # 注入 User-Agent（不覆盖调用方显式设置的值）
    headers = kwargs.setdefault("headers", {})
    if not any(k.lower() == "user-agent" for k in headers):
        headers["User-Agent"] = _USER_AGENT

    # 国内数据源绕过代理
    is_direct = any(d in url for d in _DIRECT_DOMAINS)
    if is_direct:
        kwargs.setdefault("proxies", {"http": None, "https": None})

    # 东方财富域名强制缩短超时（AkShare 默认 15s 太慢，失败后 fallback 切换迟缓）
    if any(d in url for d in _EM_DOMAINS):
        kwargs["timeout"] = _EM_TIMEOUT

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
