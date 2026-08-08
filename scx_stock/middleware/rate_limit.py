"""
@description 限流中间件，基于固定窗口计数器，复用 CacheBackend 实现。

提供端点级限流依赖：通过 FastAPI Depends 挂载到需要限流的端点
（如未来的 AI 分析端点），命中阈值时抛 RateLimitExceededError，
由 api/errors.py 统一映射为 429 + Retry-After。

设计要点：
- 算法：固定窗口计数器（按分钟），与 ai_rate_limit_per_minute 语义对齐
- 存储：复用全局 CacheBackend（Redis 优先，无 Redis 回退内存）
- 标识：默认按客户端 IP 维度限流，支持反向代理 Header
- 作用域：通过 scope 参数隔离不同业务（如 "ai" / "global"）
"""

from collections.abc import Callable
from datetime import datetime

from fastapi import Depends, Request

from scx_stock.api.deps import get_cache_dep
from scx_stock.cache.backend import CacheBackend
from scx_stock.cache.keys import rate_limit as rate_limit_key
from scx_stock.config.settings import get_settings
from scx_stock.exceptions.service import RateLimitExceededError

# 计数器 TTL 略大于窗口（分钟），确保跨窗口后键被自然清理
_WINDOW_TTL = 70


def get_client_ip(request: Request) -> str:
    """提取客户端真实 IP。

    优先信任反向代理 Header（X-Forwarded-For / X-Real-IP），
    取不到时回退到连接对端地址；均不可用时返回 "unknown"。

    :param request: FastAPI 请求对象。
    :returns: 客户端 IP 字符串。

    :example get_client_ip(request)  # "1.2.3.4"
    """
    # X-Forwarded-For: client, proxy1, proxy2 —— 取第一个非空项
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    # X-Real-IP：部分代理（如 Nginx）直接写入真实 IP
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    client = request.client
    return client.host if client else "unknown"


async def check_rate_limit(
    request: Request,
    cache: CacheBackend,
    *,
    scope: str,
    per_minute: int,
) -> None:
    """固定窗口限流检查。超限抛 RateLimitExceededError。

    :param request: FastAPI 请求（用于提取客户端 IP）。
    :param cache: 缓存后端实例。
    :param scope: 限流作用域（如 "ai"），用于隔离不同业务的计数器。
    :param per_minute: 每分钟允许的请求次数上限。
    """
    window = datetime.now().strftime("%Y%m%d%H%M")
    identity = f"{get_client_ip(request)}:{window}"
    key = rate_limit_key(scope, identity)
    count = await cache.incr(key, ttl=_WINDOW_TTL)
    if count > per_minute:
        raise RateLimitExceededError(
            f"请求过于频繁，每分钟限 {per_minute} 次", retry_after=60
        )


def ai_rate_limit() -> Callable[..., object]:
    """AI 端点限流依赖工厂。

    读取配置 ai_rate_limit_per_minute 作为每分钟阈值，作用域为 "ai"。
    在端点签名中使用：``_=Depends(ai_rate_limit())``。

    :returns: FastAPI 依赖 callable。

    :example

        >>> @router.post("/analyze")
        ... async def analyze(_=Depends(ai_rate_limit())):
        ...     ...
    """
    per_minute = get_settings().ai_rate_limit_per_minute

    async def _dep(
        request: Request,
        cache: CacheBackend = Depends(get_cache_dep),
    ) -> None:
        await check_rate_limit(
            request, cache, scope="ai", per_minute=per_minute
        )

    return _dep
