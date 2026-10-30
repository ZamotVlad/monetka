import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.cache import ping_redis
from app.db.session import ping_database

router = APIRouter(prefix="/health", tags=["health"])

Probe = Callable[[], Awaitable[bool]]


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


def get_probes(request: Request) -> dict[str, Probe]:
    state = request.app.state
    return {
        "database": partial(ping_database, state.engine),
        "redis": partial(ping_redis, state.redis),
    }


async def run_probe(probe: Probe, limit: float) -> bool:
    # A hung dependency must not hang the health check itself
    try:
        async with asyncio.timeout(limit):
            return await probe()
    except TimeoutError:
        return False


@router.get("/live")
async def live() -> dict[str, str]:
    """The process is up. Says nothing about dependencies, so restarts do not cascade."""
    return {"status": "ok"}


@router.get("/ready", response_model=Readiness)
async def ready(
    request: Request,
    response: Response,
    probes: Annotated[dict[str, Probe], Depends(get_probes)],
) -> Readiness:
    """The service can take traffic: the database and Redis answer."""
    limit = request.app.state.settings.probe_timeout_seconds
    results = await asyncio.gather(*(run_probe(probe, limit) for probe in probes.values()))
    checks = dict(zip(probes, results, strict=True))
    healthy = all(checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="ok" if healthy else "degraded", checks=checks)
