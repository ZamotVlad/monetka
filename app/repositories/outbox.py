from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, topic: str, key: str, type_: str, payload: dict[str, Any]) -> None:
        self._session.add(OutboxEvent(topic=topic, key=key, type=type_, payload=payload))

    async def lock_unpublished(self, limit: int) -> Sequence[OutboxEvent]:
        """SKIP LOCKED: a second relay takes the next batch instead of waiting for this one."""
        rows = await self._session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return rows.all()

    async def mark_published(self, ids: Sequence[int], at: datetime) -> None:
        await self._session.execute(
            update(OutboxEvent).where(OutboxEvent.id.in_(ids)).values(published_at=at)
        )

    async def backlog(self) -> int:
        count = await self._session.scalar(
            select(func.count()).where(OutboxEvent.published_at.is_(None))
        )
        return count or 0
