"""Shared arq Redis pool.

Initialised once at API startup (main.py on_startup) and closed on shutdown.
Callers import `get_redis_pool()` instead of calling `arq.create_pool` per request.
"""

from __future__ import annotations

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from apps.api.config import settings

_pool: ArqRedis | None = None


async def init_redis_pool() -> None:
    global _pool
    _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def close_redis_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def get_redis_pool() -> ArqRedis:
    if _pool is None:
        raise RuntimeError("Redis pool is not initialised. Call init_redis_pool() at startup.")
    return _pool
