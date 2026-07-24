"""
@description Provider 基类，强制同步库走线程池，对外暴露 async。
"""

from typing import Any, Callable

from anyio import to_thread


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
