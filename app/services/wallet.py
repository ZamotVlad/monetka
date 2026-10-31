from dataclasses import dataclass
from uuid import UUID

from app.db.uow import UnitOfWork
from app.domain.errors import NotFound
from app.domain.ledger import AccountKind
from app.repositories.ledger import HistoryRow


@dataclass(frozen=True, slots=True)
class Balance:
    available: int
    held: int

    @property
    def total(self) -> int:
        return self.available + self.held


class WalletService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def balance(self, user_id: UUID) -> Balance:
        accounts = await self._uow.accounts.of_user(user_id)
        if AccountKind.WALLET not in accounts:
            raise NotFound("Wallet not found")
        return Balance(
            available=accounts[AccountKind.WALLET].balance,
            held=accounts[AccountKind.HOLD].balance,
        )

    async def history(self, user_id: UUID, limit: int, before: int | None) -> list[HistoryRow]:
        accounts = await self._uow.accounts.of_user(user_id)
        return await self._uow.ledger.history(
            accounts[AccountKind.WALLET].id, accounts[AccountKind.HOLD].id, limit, before
        )
