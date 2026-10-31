from fastapi import FastAPI
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

CREDENTIALS = {"email": "olena@example.com", "password": "wrong-password"}


async def test_login_is_rate_limited(app: FastAPI, client: AsyncClient) -> None:
    app.state.settings.auth_rate_limit_per_minute = 3
    statuses = [(await client.post("/api/v1/auth/login", json=CREDENTIALS)) for _ in range(4)]
    assert [r.status_code for r in statuses] == [401, 401, 401, 429]
    assert statuses[-1].json()["error"]["code"] == "rate_limited"
    assert int(statuses[-1].headers["Retry-After"]) > 0


async def test_limiter_fails_open_without_redis(app: FastAPI, client: AsyncClient) -> None:
    class BrokenRedis:
        def pipeline(self, transaction: bool) -> None:
            raise RedisConnectionError("down")

    app.state.redis = BrokenRedis()
    response = await client.post("/api/v1/auth/login", json=CREDENTIALS)
    assert response.status_code == 401


async def test_random_authorization_header_does_not_reset_the_login_limit(
    app: FastAPI, client: AsyncClient
) -> None:
    app.state.settings.auth_rate_limit_per_minute = 2
    statuses = []
    for attempt in range(3):
        response = await client.post(
            "/api/v1/auth/login",
            json=CREDENTIALS,
            headers={"Authorization": f"Bearer fake-{attempt}"},
        )
        statuses.append(response.status_code)
    assert statuses == [401, 401, 429]
