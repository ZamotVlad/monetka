from dataclasses import dataclass
from uuid import UUID

from app.db.models import LedgerTransaction, User
from app.db.uow import UnitOfWork
from app.domain.errors import NotFound, SelfTransfer
from app.domain.ledger import PSP_ACCOUNT_ID, AccountKind, TransactionKind, move
from app.domain.money import Money
from app.repositories.ledger import HistoryRow
from app.services.ledger import LedgerService


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

    async def transfer(
        self, sender: User, recipient_email: str, amount: Money, note: str | None
    ) -> LedgerTransaction:
        recipient = await self._uow.users.by_email(recipient_email)
        if recipient is None:
            raise NotFound("No Monetka user with this email")
        if recipient.id == sender.id:
            raise SelfTransfer("You cannot send money to yourself")
        source = await self._uow.accounts.wallet_of(sender.id)
        target = await self._uow.accounts.wallet_of(recipient.id)
        details = {"from": sender.email, "to": recipient.email, "note": note}
        return await LedgerService(self._uow).post(
            TransactionKind.TRANSFER, move(source.id, target.id, amount), details
        )

    async def withdraw(self, user: User, amount: Money, card_last4: str) -> LedgerTransaction:
        wallet = await self._uow.accounts.wallet_of(user.id)
        return await LedgerService(self._uow).post(
            TransactionKind.WITHDRAWAL,
            move(wallet.id, PSP_ACCOUNT_ID, amount),
            {"card": card_last4},
        )
