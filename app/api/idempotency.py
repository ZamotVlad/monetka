from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Header, Request, Response
from pydantic import BaseModel

from app.db.uow import UnitOfWork
from app.observability import IDEMPOTENT_REPLAYS
from app.services.idempotency import IdempotencyService, fingerprint

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=255,
        description="A unique value per operation, e.g. a UUID. Retries reuse the same one.",
    ),
]


async def run_once(
    request: Request,
    response: Response,
    uow: UnitOfWork,
    scope: str,
    key: str,
    payload: BaseModel,
    operation: Callable[[], Awaitable[BaseModel]],
    status_code: int = 201,
) -> dict[str, Any]:
    async def execute() -> tuple[int, dict[str, Any]]:
        result = await operation()
        return status_code, result.model_dump(mode="json")

    stored = await IdempotencyService(uow).run(
        scope, key, fingerprint(request.url.path, payload.model_dump(mode="json")), execute
    )
    await uow.commit()
    response.status_code = stored.status_code
    if stored.replayed:
        response.headers["Idempotent-Replayed"] = "true"
        IDEMPOTENT_REPLAYS.inc()
    return stored.body
