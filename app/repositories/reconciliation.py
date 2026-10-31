from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, ReconciliationRun

# Every account whose cached balance differs from the sum of its entries
DRIFTED_ACCOUNTS = text(
    """
    SELECT a.id, a.balance, COALESCE(SUM(e.amount), 0) AS entries_total
    FROM accounts a
    LEFT JOIN ledger_entries e ON e.account_id = a.id
    GROUP BY a.id
    HAVING a.balance <> COALESCE(SUM(e.amount), 0)
    """
)

# Every transaction whose postings do not cancel out
UNBALANCED_TRANSACTIONS = text(
    """
    SELECT transaction_id, SUM(amount) AS total
    FROM ledger_entries
    GROUP BY transaction_id
    HAVING SUM(amount) <> 0
    """
)


class ReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def drifted_accounts(self) -> list[dict[str, Any]]:
        rows = await self._session.execute(DRIFTED_ACCOUNTS)
        return [
            {
                "account_id": str(row.id),
                "balance": row.balance,
                # SUM over BIGINT is NUMERIC in PostgreSQL; JSON wants a plain int
                "entries": int(row.entries_total),
            }
            for row in rows
        ]

    async def unbalanced_transactions(self) -> list[dict[str, Any]]:
        rows = await self._session.execute(UNBALANCED_TRANSACTIONS)
        return [{"transaction_id": row.transaction_id, "sum": int(row.total)} for row in rows]

    async def totals(self) -> tuple[int, int]:
        count, total = (
            await self._session.execute(select(func.count(), func.sum(Account.balance)))
        ).one()
        return count, int(total or 0)

    def add_run(self, run: ReconciliationRun) -> None:
        self._session.add(run)

    async def recent_runs(self, limit: int) -> Sequence[ReconciliationRun]:
        rows = await self._session.scalars(
            select(ReconciliationRun).order_by(ReconciliationRun.id.desc()).limit(limit)
        )
        return rows.all()
