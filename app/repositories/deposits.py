from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Deposit, ProcessedWebhook


class DepositRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, deposit: Deposit) -> None:
        self._session.add(deposit)

    async def get(self, deposit_id: UUID) -> Deposit | None:
        return await self._session.get(Deposit, deposit_id)

    async def lock(self, deposit_id: UUID) -> Deposit | None:
        return await self._session.scalar(
            select(Deposit)
            .where(Deposit.id == deposit_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def mark_webhook_processed(self, event_id: str) -> bool:
        """False when this event was already handled."""
        inserted = await self._session.scalar(
            insert(ProcessedWebhook)
            .values(event_id=event_id)
            .on_conflict_do_nothing()
            .returning(ProcessedWebhook.event_id)
        )
        return inserted is not None
