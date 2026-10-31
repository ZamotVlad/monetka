from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.config import Settings
from app.db.models import Merchant, Payment, User
from app.db.uow import UnitOfWork
from app.domain.errors import InvalidTransition, NotFound
from app.domain.ledger import AccountKind, TransactionKind, move
from app.domain.money import Money
from app.domain.payments import PaymentStatus, ensure_transition
from app.messaging.events import EventType, record_for_user
from app.services.ledger import LedgerService


def utcnow() -> datetime:
    return datetime.now(UTC)


class PaymentService:
    def __init__(self, uow: UnitOfWork, settings: Settings) -> None:
        self._uow = uow
        self._settings = settings
        self._ledger = LedgerService(uow)

    async def request(
        self, merchant: Merchant, customer_email: str, amount: Money, description: str
    ) -> Payment:
        customer = await self._uow.users.by_email(customer_email)
        if customer is None:
            raise NotFound("No Monetka user with this email")
        payment = Payment(
            merchant=merchant,
            user_id=customer.id,
            amount=amount.amount,
            description=description,
            status=PaymentStatus.PENDING,
            expires_at=utcnow() + timedelta(hours=self._settings.payment_request_ttl_hours),
        )
        self._uow.payments.add(payment)
        await self._uow.session.flush()
        self._announce(payment)
        return payment

    async def list_for_user(self, user: User, status: PaymentStatus | None) -> Sequence[Payment]:
        return await self._uow.payments.of_user(user.id, status)

    async def list_for_merchant(self, merchant: Merchant) -> Sequence[Payment]:
        return await self._uow.payments.of_merchant(merchant.id)

    async def get_for_merchant(self, merchant: Merchant, payment_id: UUID) -> Payment:
        payment = await self._uow.payments.get(payment_id)
        if payment is None or payment.merchant_id != merchant.id:
            raise NotFound("Payment not found")
        return payment

    async def confirm(self, user: User, payment_id: UUID) -> Payment:
        payment = await self._lock_for_user(user, payment_id)
        self._ensure_not_expired(payment)
        ensure_transition(PaymentStatus(payment.status), PaymentStatus.AUTHORIZED)
        accounts = await self._uow.accounts.of_user(user.id)
        await self._ledger.post(
            TransactionKind.HOLD,
            move(
                accounts[AccountKind.WALLET].id, accounts[AccountKind.HOLD].id, self._money(payment)
            ),
            self._details(payment),
            payment.id,
        )
        payment.status = PaymentStatus.AUTHORIZED
        payment.expires_at = utcnow() + timedelta(days=self._settings.hold_ttl_days)
        await self._uow.session.flush()
        self._announce(payment)
        return payment

    async def decline(self, user: User, payment_id: UUID) -> Payment:
        payment = await self._lock_for_user(user, payment_id)
        ensure_transition(PaymentStatus(payment.status), PaymentStatus.DECLINED)
        payment.status = PaymentStatus.DECLINED
        await self._uow.session.flush()
        self._announce(payment)
        return payment

    async def capture(self, merchant: Merchant, payment_id: UUID) -> Payment:
        payment = await self._lock_for_merchant(merchant, payment_id)
        self._ensure_not_expired(payment)
        ensure_transition(PaymentStatus(payment.status), PaymentStatus.CAPTURED)
        accounts = await self._uow.accounts.of_user(payment.user_id)
        merchant_account = await self._uow.merchants.account_of(merchant)
        await self._ledger.post(
            TransactionKind.CAPTURE,
            move(accounts[AccountKind.HOLD].id, merchant_account.id, self._money(payment)),
            self._details(payment),
            payment.id,
        )
        payment.status = PaymentStatus.CAPTURED
        await self._uow.session.flush()
        self._announce(payment)
        return payment

    async def void(self, merchant: Merchant, payment_id: UUID) -> Payment:
        payment = await self._lock_for_merchant(merchant, payment_id)
        await self._close(payment, PaymentStatus.VOIDED)
        return payment

    async def expire_due(self, limit: int = 100) -> int:
        payments = await self._uow.payments.lock_expired(utcnow(), limit)
        for payment in payments:
            await self._close(payment, PaymentStatus.EXPIRED)
        return len(payments)

    async def _close(self, payment: Payment, target: PaymentStatus) -> None:
        current = PaymentStatus(payment.status)
        ensure_transition(current, target)
        if current is PaymentStatus.AUTHORIZED:
            accounts = await self._uow.accounts.of_user(payment.user_id)
            await self._ledger.post(
                TransactionKind.RELEASE,
                move(
                    accounts[AccountKind.HOLD].id,
                    accounts[AccountKind.WALLET].id,
                    self._money(payment),
                ),
                self._details(payment),
                payment.id,
            )
        payment.status = target
        await self._uow.session.flush()
        self._announce(payment)

    async def _lock_for_user(self, user: User, payment_id: UUID) -> Payment:
        payment = await self._uow.payments.lock(payment_id)
        if payment is None or payment.user_id != user.id:
            raise NotFound("Payment not found")
        return payment

    async def _lock_for_merchant(self, merchant: Merchant, payment_id: UUID) -> Payment:
        payment = await self._uow.payments.lock(payment_id)
        if payment is None or payment.merchant_id != merchant.id:
            raise NotFound("Payment not found")
        return payment

    def _announce(self, payment: Payment) -> None:
        record_for_user(
            self._uow,
            payment.user_id,
            EventType.PAYMENT_UPDATED,
            {"payment_id": str(payment.id), "status": payment.status},
        )

    @staticmethod
    def _ensure_not_expired(payment: Payment) -> None:
        # The worker runs every few seconds; until then the deadline is enforced here
        if payment.expires_at <= utcnow():
            raise InvalidTransition("This payment has expired")

    @staticmethod
    def _money(payment: Payment) -> Money:
        return Money(payment.amount)

    @staticmethod
    def _details(payment: Payment) -> dict[str, str]:
        return {
            "merchant": payment.merchant.name,
            "description": payment.description,
            "payment_id": str(payment.id),
        }
