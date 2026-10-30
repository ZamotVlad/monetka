from redis.asyncio import Redis
from redis.exceptions import RedisError


def create_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


async def ping_redis(redis: Redis) -> bool:
    try:
        await redis.ping()
    except (OSError, RedisError):
        return False
    return True
