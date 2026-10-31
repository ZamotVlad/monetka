import json
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Account, OutboxEvent
from app.db.uow import UnitOfWork
from app.messaging.relay import relay_batch
from app.services.reconciliation import ReconciliationService
from app.workers.jobs import reconcile
from tests.integration.conftest import Users


class FakePublisher:
    def __init__(self, fail_after: int | None = None) -> None:
        self.sent: list[tuple[str, str, dict[str, Any]]] = []
        self._fail_after = fail_after

    async def publish(self, topic: str, key: str, value: bytes) -> None:
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise ConnectionError("broker went away")
        self.sent.append((topic, key, json.loads(value)))


async def outbox(session_factory: async_sessionmaker[AsyncSession]) -> list[OutboxEvent]:
    async with session_factory() as session:
        return list(await session.scalars(select(OutboxEvent).order_by(OutboxEvent.id)))


async def test_transfer_writes_an_event_for_each_user(
    client: AsyncClient, users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    olena_id, olena = await users.create("olena@example.com", balance=1_000)
    taras_id, _ = await users.create("taras@example.com")
    await client.post(
        "/api/v1/transfers",
        json={"to_email": "taras@example.com", "amount": 100},
        headers=olena | {"Idempotency-Key": str(uuid4())},
    )

    events = await outbox(session_factory)
    transfer_events = [e for e in events if e.payload.get("kind") == "transfer"]
    assert {e.key for e in transfer_events} == {str(olena_id), str(taras_id)}
    assert all(e.type == "wallet.changed" for e in transfer_events)


async def test_failed_operation_leaves_no_event(
    client: AsyncClient, users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _, olena = await users.create("olena@example.com", balance=100)
    await users.create("taras@example.com")
    before = len(await outbox(session_factory))

    response = await client.post(
        "/api/v1/transfers",
        json={"to_email": "taras@example.com", "amount": 500},
        headers=olena | {"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 422
    assert len(await outbox(session_factory)) == before


async def test_relay_publishes_in_order_and_marks_events(
    users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user_id, _ = await users.create("olena@example.com", balance=100)
    await users.fund(user_id, 200)
    publisher = FakePublisher()

    assert await relay_batch(session_factory, publisher) == 2
    assert await relay_batch(session_factory, publisher) == 0

    assert [message["type"] for _, _, message in publisher.sent] == ["wallet.changed"] * 2
    ids = [message["id"] for _, _, message in publisher.sent]
    assert ids == sorted(ids)
    assert all(e.published_at is not None for e in await outbox(session_factory))


async def test_relay_retries_the_batch_after_a_broker_failure(
    users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user_id, _ = await users.create("olena@example.com", balance=100)
    await users.fund(user_id, 200)

    with pytest.raises(ConnectionError):
        await relay_batch(session_factory, FakePublisher(fail_after=1))
    assert all(e.published_at is None for e in await outbox(session_factory))

    publisher = FakePublisher()
    assert await relay_batch(session_factory, publisher) == 2


async def test_reconciliation_passes_on_healthy_books(
    users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await users.create("olena@example.com", balance=5_000)
    assert await reconcile(session_factory) is True


async def test_reconciliation_catches_a_tampered_balance(
    users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    olena, _ = await users.create("olena@example.com", balance=5_000)
    async with session_factory() as session:
        await session.execute(
            update(Account)
            .where(Account.user_id == olena, Account.kind == "wallet")
            .values(balance=Account.balance + 1)
        )
        await session.commit()

    async with UnitOfWork(session_factory) as uow:
        run = await ReconciliationService(uow).run()

    assert run.ok is False
    assert run.books_total == 1
    assert len(run.problems["drifted_accounts"]) == 1


async def test_reconciliation_catches_an_unbalanced_transaction(
    users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await users.create("olena@example.com", balance=5_000)
    async with session_factory() as session:
        await session.execute(text("UPDATE ledger_entries SET amount = amount + 1 WHERE id = 1"))
        await session.commit()

    async with UnitOfWork(session_factory) as uow:
        run = await ReconciliationService(uow).run()

    assert run.ok is False
    assert run.problems["unbalanced_transactions"]
