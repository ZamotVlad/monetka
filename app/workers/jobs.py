import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.uow import UnitOfWork
from app.services.payments import PaymentService

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
