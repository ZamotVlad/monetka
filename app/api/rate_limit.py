import hashlib
import logging
import time

from fastapi import Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.api.errors import ApiError
from app.config import Settings

logger = logging.getLogger(__name__)


class RateLimit:
    """Fixed-window limiter in Redis: one counter per client per minute.

    Clients are told apart by their token when they have one, by IP otherwise.
    If Redis is down the request goes through: a missing limiter is better than a
    wallet nobody can use.
    """

    def __init__(self, name: str, setting: str, window_seconds: int = 60) -> None:
        self._name = name
        self._setting = setting
        self._window = window_seconds

    async def __call__(self, request: Request) -> None:
        settings: Settings = request.app.state.settings
        limit: int = getattr(settings, self._setting)
        redis: Redis = request.app.state.redis
        window = int(time.time() // self._window)
        key = f"rate:{self._name}:{self._client_id(request)}:{window}"
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, self._window)
                count, _ = await pipe.execute()
        except (RedisError, OSError):
            logger.warning("rate limiter unavailable, letting the request through")
            return
        if count > limit:
            retry_after = self._window - int(time.time()) % self._window
            raise ApiError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limited",
                "Too many requests, try again in a moment",
                headers={"Retry-After": str(retry_after)},
            )

    @staticmethod
    def _client_id(request: Request) -> str:
        token = request.headers.get("authorization")
        if token:
            return hashlib.sha256(token.encode()).hexdigest()[:16]
        return request.client.host if request.client else "unknown"


auth_limit = RateLimit("auth", "auth_rate_limit_per_minute")
money_limit = RateLimit("money", "money_rate_limit_per_minute")
