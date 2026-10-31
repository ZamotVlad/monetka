from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LedgerEntry, LedgerTransaction
from app.domain.ledger import Posting, TransactionKind


@dataclass(frozen=True, slots=True)
class HistoryRow:
    id: int
    kind: str
    details: dict[str, Any]
    created_at: datetime
    wallet_delta: int
    held_delta: int


class LedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        kind: TransactionKind,
        postings: Sequence[Posting],
        details: dict[str, Any],
    ) -> LedgerTransaction:
        transaction = LedgerTransaction(
            kind=kind,
            details=details,
            entries=[
                LedgerEntry(account_id=posting.account_id, amount=posting.amount.amount)
                for posting in postings
            ],
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction

    async def history(
        self, wallet_id: UUID, hold_id: UUID, limit: int, before: int | None
    ) -> list[HistoryRow]:
        """One row per transaction, with what it did to the wallet and to the reserve."""
        wallet_delta = func.sum(
            case((LedgerEntry.account_id == wallet_id, LedgerEntry.amount), else_=0)
        )
        held_delta = func.sum(
            case((LedgerEntry.account_id == hold_id, LedgerEntry.amount), else_=0)
        )
        query = (
            select(
                LedgerTransaction.id,
                LedgerTransaction.kind,
                LedgerTransaction.details,
                LedgerTransaction.created_at,
                wallet_delta,
                held_delta,
            )
            .join(LedgerEntry, LedgerEntry.transaction_id == LedgerTransaction.id)
            .where(LedgerEntry.account_id.in_([wallet_id, hold_id]))
            .group_by(LedgerTransaction.id)
            .order_by(LedgerTransaction.id.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(LedgerTransaction.id < before)
        rows = await self._session.execute(query)
        return [HistoryRow(*row) for row in rows]
