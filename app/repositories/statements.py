from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, LedgerEntry, LedgerTransaction, Statement


class StatementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user_id: UUID, period: str, object_key: str, rows: int) -> Statement:
        """Regenerating a month replaces the old file instead of adding a second one."""
        statement = await self._session.scalar(
            insert(Statement)
            .values(user_id=user_id, period=period, object_key=object_key, rows=rows)
            .on_conflict_do_update(
                index_elements=[Statement.user_id, Statement.period],
                set_={"object_key": object_key, "rows": rows},
            )
            .returning(Statement)
        )
        assert isinstance(statement, Statement)
        return statement

    async def of_user(self, user_id: UUID) -> Sequence[Statement]:
        rows = await self._session.scalars(
            select(Statement).where(Statement.user_id == user_id).order_by(Statement.period.desc())
        )
        return rows.all()

    async def users_missing(self, period: str, since: datetime, until: datetime) -> list[UUID]:
        """Users who had activity in the period but have no statement for it yet."""
        active = (
            select(Account.user_id)
            .join(LedgerEntry, LedgerEntry.account_id == Account.id)
            .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
            .where(
                Account.user_id.is_not(None),
                LedgerTransaction.created_at >= since,
                LedgerTransaction.created_at < until,
            )
            .distinct()
        )
        has_statement = exists().where(
            Statement.user_id == Account.user_id, Statement.period == period
        )
        rows = await self._session.scalars(active.where(~has_statement))
        return [user_id for user_id in rows if user_id is not None]
