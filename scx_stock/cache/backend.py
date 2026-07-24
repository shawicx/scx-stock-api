"""
@description 缓存后端，封装 Redis 与内存实现，统一对外接口。
"""

import json
from typing import Any

import redis.asyncio as aioredis

from scx_stock.config.settings import get_settings


class CacheBackend:
    """缓存后端抽象基类。"""

    async def get(self, key: str) -> Any:
        """读取缓存值。

        :param key: 缓存键。
        :returns: 反序列化后的值，未命中返回 None。
        """
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """写入缓存值。

        :param key: 缓存键。
        :param value: 待缓存值（可序列化）。
        :param ttl: 过期时间（秒）。
        """
        raise NotImplementedError

    async def close(self) -> None:
        """释放连接资源。"""
        return None


class RedisCache(CacheBackend):
    """基于 redis.asyncio 的缓存实现。

    :param client: 已建立的 redis 异步客户端。
    """

    def __init__(self, client: aioredis.Redis) -> None:  # type: ignore[type-arg]
        self._client = client

    async def get(self, key: str) -> Any:
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)

    async def close(self) -> None:
        await self._client.aclose()


class MemoryCache(CacheBackend):
    """内存缓存实现，开发环境无 Redis 时回退使用。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Any:
        item = self._store.get(key)
        if item is None:
            return None
        value, expire_at = item
        import time

        if expire_at and expire_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        import time

        self._store[key] = (value, time.time() + ttl)

    async def close(self) -> None:
        self._store.clear()


_cache: CacheBackend | None = None


async def get_cache() -> CacheBackend:
    """获取全局缓存单例。无 Redis 时回退到内存缓存。

    :returns: CacheBackend 实例。
    """
    global _cache
    if _cache is not None:
        return _cache

    s = get_settings()
    try:
        client = aioredis.from_url(
            f"redis://{':' + s.redis_password + '@' if s.redis_password else ''}"
            f"{s.redis_host}:{s.redis_port}/{s.redis_db}",
            decode_responses=True,
            socket_connect_timeout=2,
        )
        await client.ping()
        _cache = RedisCache(client)
    except Exception:
        # 开发环境回退到内存缓存
        _cache = MemoryCache()
    return _cache
