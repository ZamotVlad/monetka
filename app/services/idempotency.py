import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.db.uow import UnitOfWork
from app.domain.errors import IdempotencyConflict


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    body: dict[str, Any]
    replayed: bool


def fingerprint(path: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"path": path, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyService:
    """Runs an operation at most once per key, and replays its response to retries.

    The key row and the money movement share one transaction: either both are saved or
    neither is. A failed attempt leaves no key behind, so the client can simply retry.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def run(
        self,
        scope: str,
        key: str,
        request_hash: str,
        operation: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
    ) -> StoredResponse:
        existing = await self._uow.idempotency.claim(scope, key, request_hash)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyConflict("This Idempotency-Key was used for another request")
            assert existing.status_code is not None and existing.response_body is not None
            return StoredResponse(existing.status_code, existing.response_body, replayed=True)
        status_code, body = await operation()
        await self._uow.idempotency.save_response(scope, key, status_code, body)
        return StoredResponse(status_code, body, replayed=False)
