import asyncio

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.health import Probe, get_probes
from app.cache import create_redis, ping_redis
from app.db.session import create_engine, ping_database


def use_probes(app: FastAPI, **results: bool) -> None:
    def make(result: bool) -> Probe:
        async def probe() -> bool:
            return result

        return probe

    app.dependency_overrides[get_probes] = lambda: {name: make(r) for name, r in results.items()}


async def test_live_does_not_touch_dependencies(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_all_dependencies_answer(app: FastAPI, client: AsyncClient) -> None:
    use_probes(app, database=True, redis=True)

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": True, "redis": True}}


async def test_ready_is_503_when_a_dependency_is_down(app: FastAPI, client: AsyncClient) -> None:
    use_probes(app, database=True, redis=False)

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"database": True, "redis": False}}


async def test_ready_treats_a_hung_probe_as_down(app: FastAPI, client: AsyncClient) -> None:
    async def hangs() -> bool:
        await asyncio.sleep(10)
        return True

    app.state.settings.probe_timeout_seconds = 0.05
    app.dependency_overrides[get_probes] = lambda: {"database": hangs}

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False}


async def test_ping_database_reports_unreachable_server() -> None:
    engine = create_engine("postgresql+asyncpg://user:pass@127.0.0.1:1/nothing")
    try:
        assert await ping_database(engine) is False
    finally:
        await engine.dispose()


async def test_ping_redis_reports_unreachable_server() -> None:
    redis = create_redis("redis://127.0.0.1:1/0")
    try:
        assert await ping_redis(redis) is False
    finally:
        await redis.aclose()
