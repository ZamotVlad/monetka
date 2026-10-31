from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account
from app.domain.errors import NotFound
from app.domain.ledger import AccountKind


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, account: Account) -> None:
        self._session.add(account)

    async def of_user(self, user_id: UUID) -> dict[AccountKind, Account]:
        rows = await self._session.scalars(select(Account).where(Account.user_id == user_id))
        return {AccountKind(account.kind): account for account in rows}

    async def wallet_of(self, user_id: UUID) -> Account:
        account = await self._session.scalar(
            select(Account).where(Account.user_id == user_id, Account.kind == AccountKind.WALLET)
        )
        if account is None:
            raise NotFound("Wallet not found")
        return account

    async def lock(self, account_ids: Iterable[UUID]) -> dict[UUID, Account]:
        """Lock rows for the rest of the transaction.

        Ordering by id means two transfers A->B and B->A lock in the same order and wait for
        each other instead of deadlocking. populate_existing refreshes rows the session
        already loaded, otherwise we would compute on a balance read before the lock.
        """
        rows = await self._session.scalars(
            select(Account)
            .where(Account.id.in_(set(account_ids)))
            .order_by(Account.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {account.id: account for account in rows}
