import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.uow import UnitOfWork
from app.messaging.relay import Publisher, relay_batch
from app.services.payments import PaymentService
from app.services.reconciliation import ReconciliationService

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
        logger.info("expired %d payments", total)
    return total


async def relay_outbox(
    session_factory: async_sessionmaker[AsyncSession], publisher: Publisher
) -> int:
    total = 0
    while (sent := await relay_batch(session_factory, publisher)) > 0:
        total += sent
    return total


async def reconcile(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    async with UnitOfWork(session_factory) as uow:
        run = await ReconciliationService(uow).run()
        await uow.commit()
    if run.ok:
        logger.info("books balanced across %d accounts", run.accounts_checked)
    else:
        logger.error("books do NOT balance: %s", run.problems)
    return run.ok
