from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, LedgerEntry, LedgerTransaction, Merchant, User
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
        payment_id: UUID | None = None,
    ) -> LedgerTransaction:
        transaction = LedgerTransaction(
            kind=kind,
            details=details,
            payment_id=payment_id,
            entries=[
                LedgerEntry(account_id=posting.account_id, amount=posting.amount.amount)
                for posting in postings
            ],
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction

    async def history(
        self,
        wallet_id: UUID,
        hold_id: UUID,
        limit: int | None,
        before: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[HistoryRow]:
        """One row per transaction, with what it did to the wallet and to the reserve."""
        # SUM over BIGINT gives NUMERIC in PostgreSQL; cast back to get Python ints
        wallet_delta = cast(
            func.sum(case((LedgerEntry.account_id == wallet_id, LedgerEntry.amount), else_=0)),
            BigInteger,
        )
        held_delta = cast(
            func.sum(case((LedgerEntry.account_id == hold_id, LedgerEntry.amount), else_=0)),
            BigInteger,
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
        if since is not None:
            query = query.where(LedgerTransaction.created_at >= since)
        if until is not None:
            query = query.where(LedgerTransaction.created_at < until)
        rows = await self._session.execute(query)
        return [HistoryRow(*row) for row in rows]

    async def journal(self, limit: int, before: int | None) -> list["JournalEntry"]:
        return await _journal(self._session, limit, before)


@dataclass(frozen=True, slots=True)
class JournalLine:
    account_id: UUID
    account_kind: str
    owner: str
    amount: int


@dataclass(frozen=True, slots=True)
class JournalEntry:
    id: int
    kind: str
    details: dict[str, Any]
    created_at: datetime
    lines: list[JournalLine]


async def _journal(session: AsyncSession, limit: int, before: int | None) -> list[JournalEntry]:
    """The raw books: each transaction with all of its postings.

    Two queries for the whole page, not one per transaction: the N+1 trap is easy to fall
    into with an ORM relationship here.
    """
    query = select(LedgerTransaction).order_by(LedgerTransaction.id.desc()).limit(limit)
    if before is not None:
        query = query.where(LedgerTransaction.id < before)
    transactions = (await session.scalars(query)).all()
    if not transactions:
        return []
    owner = func.coalesce(User.email, Merchant.name, literal("card provider"))
    rows = await session.execute(
        select(LedgerEntry.transaction_id, Account.id, Account.kind, owner, LedgerEntry.amount)
        .join(Account, Account.id == LedgerEntry.account_id)
        .outerjoin(User, User.id == Account.user_id)
        .outerjoin(Merchant, Merchant.id == Account.merchant_id)
        .where(LedgerEntry.transaction_id.in_([t.id for t in transactions]))
        .order_by(LedgerEntry.id)
    )
    lines: dict[int, list[JournalLine]] = {}
    for transaction_id, account_id, kind, label, amount in rows:
        lines.setdefault(transaction_id, []).append(JournalLine(account_id, kind, label, amount))
    return [
        JournalEntry(t.id, t.kind, t.details, t.created_at, lines.get(t.id, []))
        for t in transactions
    ]
