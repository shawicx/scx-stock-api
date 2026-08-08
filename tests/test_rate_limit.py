"""
@description 限流策略测试：覆盖 CacheBackend.incr、客户端 IP 提取、限流命中、健康检查不受影响。
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from scx_stock.cache.backend import MemoryCache
from scx_stock.cache.keys import rate_limit as rate_limit_key
from scx_stock.exceptions.service import RateLimitExceededError
from scx_stock.middleware.rate_limit import get_client_ip


# ---------------------------------------------------------------------------
# CacheBackend.incr 单元测试（MemoryCache）
# ---------------------------------------------------------------------------


async def test_memory_incr_starts_from_one():
    """首次自增返回 1。"""
    cache = MemoryCache()
    assert await cache.incr("k", ttl=70) == 1


async def test_memory_incr_increments():
    """连续自增逐次递增。"""
    cache = MemoryCache()
    assert await cache.incr("k", ttl=70) == 1
    assert await cache.incr("k", ttl=70) == 2
    assert await cache.incr("k", ttl=70) == 3


async def test_memory_incr_independent_keys():
    """不同 key 计数相互独立。"""
    cache = MemoryCache()
    await cache.incr("a", ttl=70)
    await cache.incr("a", ttl=70)
    assert await cache.incr("b", ttl=70) == 1
    assert await cache.incr("a", ttl=70) == 3


async def test_memory_incr_expires_after_ttl():
    """窗口过期后计数重置为 1。"""
    import time

    cache = MemoryCache()
    await cache.incr("k", ttl=1)
    await cache.incr("k", ttl=1)
    # 等待 TTL 过期（直接操作内部存储模拟过期）
    cache._store["k"] = (cache._store["k"][0], time.time() - 1)
    assert await cache.incr("k", ttl=70) == 1


# ---------------------------------------------------------------------------
# 缓存键格式
# ---------------------------------------------------------------------------


def test_rate_limit_key_format():
    """限流键遵循 scx:ratelimit:{scope}:{identity} 格式。"""
    key = rate_limit_key("ai", "1.2.3.4:202608060905")
    assert key == "scx:ratelimit:ai:1.2.3.4:202608060905"


# ---------------------------------------------------------------------------
# RateLimitExceededError 属性
# ---------------------------------------------------------------------------


def test_rate_limit_error_carries_retry_after():
    """异常携带 retry_after 属性，默认 60 秒。"""
    err = RateLimitExceededError("too many")
    assert err.retry_after == 60

    err2 = RateLimitExceededError("too many", retry_after=30)
    assert err2.retry_after == 30


# ---------------------------------------------------------------------------
# get_client_ip 解析逻辑
# ---------------------------------------------------------------------------


def _make_request(headers: dict[str, str] | None = None, client_host: str = "10.0.0.1"):
    """构造带指定 Header / 对端地址的伪请求对象。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=client_host),
    )


def test_client_ip_from_forwarded_for():
    """优先取 X-Forwarded-For 首段。"""
    req = _make_request({"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
    assert get_client_ip(req) == "1.2.3.4"


def test_client_ip_from_real_ip():
    """无 X-Forwarded-For 时回退 X-Real-IP。"""
    req = _make_request({"x-real-ip": "9.9.9.9"})
    assert get_client_ip(req) == "9.9.9.9"


def test_client_ip_fallback_to_client_host():
    """无代理 Header 时回退连接对端地址。"""
    req = _make_request({}, client_host="10.0.0.1")
    assert get_client_ip(req) == "10.0.0.1"


def test_client_ip_unknown_when_no_client():
    """无 client 信息时返回 unknown。"""
    from types import SimpleNamespace

    req = SimpleNamespace(headers={}, client=None)
    assert get_client_ip(req) == "unknown"


# ---------------------------------------------------------------------------
# 限流命中端到端测试（临时 FastAPI app + check_rate_limit）
# ---------------------------------------------------------------------------


def _build_rate_limit_app(per_minute: int) -> FastAPI:
    """构造挂载限流端点的临时 app。

    直接绑定一个全新 MemoryCache（避免跨测试共享计数），
    并内联一个读取指定阈值的限流依赖。

    :param per_minute: 每分钟允许的请求次数。
    :returns: 装配好的 FastAPI 应用。
    """
    from scx_stock.middleware.rate_limit import check_rate_limit

    cache = MemoryCache()
    app = FastAPI()

    @app.get("/ping")
    async def ping(request: Request):
        await check_rate_limit(request, cache, scope="ai", per_minute=per_minute)
        return {"code": 0, "message": "ok", "data": {"pong": True}}

    return app


@pytest.fixture
def rate_limit_app():
    """阈值=2/分钟的限流测试 app。"""
    return _build_rate_limit_app(per_minute=2)


def test_rate_limit_allows_within_threshold(rate_limit_app):
    """阈值内请求正常返回 200。"""
    with TestClient(rate_limit_app) as c:
        r1 = c.get("/ping")
        r2 = c.get("/ping")
        assert r1.status_code == 200
        assert r2.status_code == 200


def test_rate_limit_blocks_when_exceeded(rate_limit_app):
    """超过阈值返回 429 + code 42901 + Retry-After 头。"""
    # 临时 app 需注册异常处理器才能产出统一 429 响应
    from scx_stock.api.errors import register_exception_handlers

    register_exception_handlers(rate_limit_app)
    with TestClient(rate_limit_app) as c:
        c.get("/ping")
        c.get("/ping")
        r3 = c.get("/ping")
        assert r3.status_code == 429
        body = r3.json()
        assert body["code"] == 42901
        assert body["data"] is None
        assert r3.headers.get("retry-after") == "60"


def test_rate_limit_identity_isolated_by_ip(rate_limit_app):
    """不同 IP 各自独立计数（阈值内均不触发 429）。"""
    with TestClient(rate_limit_app) as c:
        # IP A 用满 2 次
        c.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"})
        c.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"})
        # IP B 应仍可用
        r = c.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 健康检查 / 运维端点不受限流影响
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def main_app_client():
    """主应用 client（验证 /health、/admin 不被限流）。"""
    from scx_stock.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health_not_rate_limited(main_app_client):
    """/health 多次访问不返回 429。"""
    for _ in range(30):
        r = main_app_client.get("/health")
        assert r.status_code == 200
