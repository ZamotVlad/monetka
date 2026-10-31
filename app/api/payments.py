from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SettingsDep, UoW
from app.api.rate_limit import money_limit
from app.api.schemas import PaymentOut
from app.domain.payments import PaymentStatus
from app.services.payments import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("")
async def list_payments(
    user: CurrentUser, uow: UoW, settings: SettingsDep, status: PaymentStatus | None = None
) -> list[PaymentOut]:
    payments = await PaymentService(uow, settings).list_for_user(user, status)
    return [PaymentOut.model_validate(payment) for payment in payments]


@router.post("/{payment_id}/confirm", dependencies=[Depends(money_limit)])
async def confirm(
    payment_id: UUID, user: CurrentUser, uow: UoW, settings: SettingsDep
) -> PaymentOut:
    """Safe to retry: a second confirm hits the state machine, not the wallet."""
    payment = await PaymentService(uow, settings).confirm(user, payment_id)
    await uow.commit()
    return PaymentOut.model_validate(payment)


@router.post("/{payment_id}/decline")
async def decline(
    payment_id: UUID, user: CurrentUser, uow: UoW, settings: SettingsDep
) -> PaymentOut:
    payment = await PaymentService(uow, settings).decline(user, payment_id)
    await uow.commit()
    return PaymentOut.model_validate(payment)
