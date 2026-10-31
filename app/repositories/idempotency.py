from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, scope: str, key: str, request_hash: str) -> IdempotencyKey | None:
        """Insert the key, or return the row someone else already stored.

        If another transaction inserted the same key and has not committed yet, PostgreSQL
        makes this INSERT wait on the unique index. When that request commits we see its
        saved response; when it rolls back our insert goes through. No duplicate ever runs.
        """
        inserted = await self._session.scalar(
            insert(IdempotencyKey)
            .values(scope=scope, key=key, request_hash=request_hash)
            .on_conflict_do_nothing()
            .returning(IdempotencyKey.key)
        )
        if inserted is not None:
            return None
        return await self._session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key)
        )

    async def save_response(
        self, scope: str, key: str, status_code: int, body: dict[str, Any]
    ) -> None:
        await self._session.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.scope == scope, IdempotencyKey.key == key)
            .values(status_code=status_code, response_body=body)
        )
