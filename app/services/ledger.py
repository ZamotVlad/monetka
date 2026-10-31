from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.db.models import LedgerTransaction
from app.db.uow import UnitOfWork
from app.domain import ledger
from app.domain.errors import NotFound
from app.domain.ledger import Posting, TransactionKind


class LedgerService:
    """The only code that changes balances. Everything else asks it to post a transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def post(
        self,
        kind: TransactionKind,
        postings: Sequence[Posting],
        details: dict[str, Any] | None = None,
        payment_id: UUID | None = None,
    ) -> LedgerTransaction:
        ledger.validate(postings)
        accounts = await self._uow.accounts.lock(posting.account_id for posting in postings)
        if len(accounts) != len({posting.account_id for posting in postings}):
            raise NotFound("Account not found")
        new_balances = ledger.apply(
            {account.id: account.balance for account in accounts.values()},
            postings,
            overdraft_allowed={a.id for a in accounts.values() if a.allow_negative},
        )
        for account in accounts.values():
            account.balance = new_balances[account.id]
        return await self._uow.ledger.add(kind, postings, details or {}, payment_id)
