from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.domain.payments import PaymentStatus

OPEN_STATUSES = (PaymentStatus.PENDING, PaymentStatus.AUTHORIZED)


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, payment: Payment) -> None:
        self._session.add(payment)

    async def lock(self, payment_id: UUID) -> Payment | None:
        """Capture, void and expiry can race for one payment; the row lock picks a winner."""
        return await self._session.scalar(
            select(Payment)
            .where(Payment.id == payment_id)
            .with_for_update(of=Payment)
            .execution_options(populate_existing=True)
        )

    async def get(self, payment_id: UUID) -> Payment | None:
        return await self._session.get(Payment, payment_id)

    async def of_user(self, user_id: UUID, status: PaymentStatus | None) -> Sequence[Payment]:
        query = select(Payment).where(Payment.user_id == user_id)
        if status is not None:
            query = query.where(Payment.status == status)
        rows = await self._session.scalars(query.order_by(Payment.created_at.desc()).limit(50))
        return rows.all()

    async def of_merchant(self, merchant_id: UUID) -> Sequence[Payment]:
        rows = await self._session.scalars(
            select(Payment)
            .where(Payment.merchant_id == merchant_id)
            .order_by(Payment.created_at.desc())
            .limit(50)
        )
        return rows.all()

    async def lock_expired(self, now: datetime, limit: int) -> Sequence[Payment]:
        """SKIP LOCKED lets several workers share the work without waiting on each other."""
        rows = await self._session.scalars(
            select(Payment)
            .where(Payment.status.in_(OPEN_STATUSES), Payment.expires_at <= now)
            .order_by(Payment.expires_at)
            .limit(limit)
            .with_for_update(of=Payment, skip_locked=True)
        )
        return rows.all()
