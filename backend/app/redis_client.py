import asyncio
from redis import Redis
import redis.asyncio as aioredis
from app.config import settings

redis_client: Redis | None = None
async_redis_client: aioredis.Redis | None = None

def get_redis() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client


def get_async_redis() -> aioredis.Redis:
    global async_redis_client
    if async_redis_client is None:
        async_redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return async_redis_client


async def run_sync_redis(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def get_redis_password() -> str:
    from app.config import settings
    import os
    return os.getenv("REDIS_PASSWORD", "")
