import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.config import Settings
from app.db.models import Deposit, User
from app.db.uow import UnitOfWork
from app.domain.errors import NotFound
from app.domain.ledger import PSP_ACCOUNT_ID, TransactionKind, move
from app.domain.money import Money
from app.integrations import psp
from app.messaging.events import EventType, record_for_user
from app.services.ledger import LedgerService
from app.services.payments import utcnow

logger = logging.getLogger(__name__)


class DepositStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    event_id: str
    deposit_id: UUID
    status: DepositStatus
    amount: int
    card_last4: str


class DepositService:
    def __init__(self, uow: UnitOfWork, settings: Settings) -> None:
        self._uow = uow
        self._settings = settings

    async def start(self, user: User, amount: Money) -> tuple[Deposit, str]:
        deposit = Deposit(user_id=user.id, amount=amount.amount, status=DepositStatus.PENDING)
        self._uow.deposits.add(deposit)
        await self._uow.session.flush()
        return deposit, self.checkout_url(deposit)

    def checkout_url(self, deposit: Deposit) -> str:
        data, signature = psp.encode_checkout(
            self._settings.psp_secret,
            {
                "deposit_id": str(deposit.id),
                "amount": deposit.amount,
                "currency": "UAH",
                "callback_url": self._settings.psp_callback_url,
                "return_url": f"{self._settings.public_url}/app.html?deposit={deposit.id}",
            },
        )
        return f"{self._settings.psp_checkout_url}?data={data}&signature={signature}"

    async def get(self, user: User, deposit_id: UUID) -> Deposit:
        deposit = await self._uow.deposits.get(deposit_id)
        if deposit is None or deposit.user_id != user.id:
            raise NotFound("Deposit not found")
        return deposit

    async def handle(self, event: ProviderEvent) -> str:
        """Apply a provider event once, whatever order or how many times it arrives."""
        if not await self._uow.deposits.mark_webhook_processed(event.event_id):
            return "duplicate"
        deposit = await self._uow.deposits.lock(event.deposit_id)
        if deposit is None:
            logger.warning("webhook for unknown deposit %s", event.deposit_id)
            return "unknown_deposit"
        if deposit.status != DepositStatus.PENDING:
            # A late "failed" after "succeeded" must not undo a finished top-up
            return "already_final"
        deposit.completed_at = utcnow()
        if event.status is DepositStatus.SUCCEEDED and event.amount != deposit.amount:
            logger.error("deposit %s: provider amount %s differs", deposit.id, event.amount)
            deposit.status = DepositStatus.FAILED
            return "amount_mismatch"
        if event.status is DepositStatus.SUCCEEDED:
            wallet = await self._uow.accounts.wallet_of(deposit.user_id)
            await LedgerService(self._uow).post(
                TransactionKind.DEPOSIT,
                move(PSP_ACCOUNT_ID, wallet.id, Money(deposit.amount)),
                {"card": event.card_last4, "deposit_id": str(deposit.id)},
            )
        deposit.status = event.status
        await self._uow.session.flush()
        record_for_user(
            self._uow,
            deposit.user_id,
            EventType.DEPOSIT_UPDATED,
            {"deposit_id": str(deposit.id), "status": deposit.status},
        )
        return "processed"
