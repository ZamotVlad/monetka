from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select

from app.db.models import Account, ReconciliationRun, User
from app.db.uow import UnitOfWork
from app.repositories.ledger import JournalEntry


@dataclass(frozen=True, slots=True)
class Overview:
    users: int
    balances: dict[str, int]
    books_total: int
    outbox_backlog: int
    last_run: ReconciliationRun | None


class OpsService:
    """Read-only views for operators. Shows the books exactly as they are stored."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def overview(self) -> Overview:
        session = self._uow.session
        users = await session.scalar(select(func.count()).select_from(User)) or 0
        rows = await session.execute(
            select(Account.kind, func.sum(Account.balance)).group_by(Account.kind)
        )
        balances = {kind: int(total) for kind, total in rows}
        runs = await self._uow.reconciliation.recent_runs(1)
        return Overview(
            users=users,
            balances=balances,
            books_total=sum(balances.values()),
            outbox_backlog=await self._uow.outbox.backlog(),
            last_run=runs[0] if runs else None,
        )

    async def journal(self, limit: int, before: int | None) -> list[JournalEntry]:
        return await self._uow.ledger.journal(limit, before)

    async def runs(self, limit: int) -> Sequence[ReconciliationRun]:
        return await self._uow.reconciliation.recent_runs(limit)
