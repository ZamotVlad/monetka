import json
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import OutboxEvent
from app.db.uow import UnitOfWork
from app.services.payments import utcnow


class Publisher(Protocol):
    async def publish(self, topic: str, key: str, value: bytes) -> None: ...


def serialize(event: OutboxEvent) -> bytes:
    message = {
        "id": event.id,
        "type": event.type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }
    return json.dumps(message).encode()


async def relay_batch(
    session_factory: async_sessionmaker[AsyncSession], publisher: Publisher, limit: int = 100
) -> int:
    """Ship one batch of outbox rows to Kafka, then mark them sent.

    If the process dies between the send and the commit, the batch goes out again on the
    next run. That is at-least-once delivery: consumers must tolerate duplicates, and they
    can, because every message carries its outbox id.
    """
    async with UnitOfWork(session_factory) as uow:
        events = await uow.outbox.lock_unpublished(limit)
        for event in events:
            await publisher.publish(event.topic, event.key, serialize(event))
        if events:
            await uow.outbox.mark_published([event.id for event in events], utcnow())
            await uow.commit()
        return len(events)
