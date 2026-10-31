import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.uow import UnitOfWork
from app.integrations.storage import FileStorage
from app.messaging.relay import Publisher, relay_batch
from app.observability import (
    BOOKS_BALANCED,
    OUTBOX_BACKLOG,
    OUTBOX_PUBLISHED,
    PAYMENTS_EXPIRED,
)
from app.services.payments import PaymentService, utcnow
from app.services.reconciliation import ReconciliationService
from app.services.statements import StatementService, previous_period

logger = logging.getLogger(__name__)


async def expire_payments(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> int:
    """Close requests nobody answered and give back reserves nobody captured."""
    total = 0
    while True:
        async with UnitOfWork(session_factory) as uow:
            count = await PaymentService(uow, settings).expire_due(limit=100)
            await uow.commit()
        total += count
        if count < 100:
            break
    if total:
        PAYMENTS_EXPIRED.inc(total)
        logger.info("expired %d payments", total)
    return total


async def relay_outbox(
    session_factory: async_sessionmaker[AsyncSession], publisher: Publisher
) -> int:
    total = 0
    while (sent := await relay_batch(session_factory, publisher)) > 0:
        total += sent
        OUTBOX_PUBLISHED.inc(sent)
    async with UnitOfWork(session_factory) as uow:
        OUTBOX_BACKLOG.set(await uow.outbox.backlog())
    return total


async def reconcile(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    async with UnitOfWork(session_factory) as uow:
        run = await ReconciliationService(uow).run()
        await uow.commit()
    BOOKS_BALANCED.set(1 if run.ok else 0)
    if run.ok:
        logger.info("books balanced across %d accounts", run.accounts_checked)
    else:
        logger.error("books do NOT balance: %s", run.problems)
    return run.ok


async def monthly_statements(
    session_factory: async_sessionmaker[AsyncSession], storage: FileStorage
) -> int:
    """Hourly and idempotent: generates only the statements still missing for last month."""
    period = previous_period(utcnow())
    async with UnitOfWork(session_factory) as uow:
        due = await StatementService(uow, storage).users_due(period)
    for user_id in due:
        async with UnitOfWork(session_factory) as uow:
            await StatementService(uow, storage).generate(user_id, period)
            await uow.commit()
    if due:
        logger.info("generated %d statements for %s", len(due), period)
    return len(due)
