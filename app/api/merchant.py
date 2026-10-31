from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentMerchant, SettingsDep, UoW
from app.api.idempotency import IdempotencyKey, run_once
from app.api.schemas import MerchantPaymentOut, PaymentRequestIn
from app.domain.money import Money
from app.services.payments import PaymentService

router = APIRouter(prefix="/merchant/payments", tags=["merchant"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def request_payment(
    body: PaymentRequestIn,
    merchant: CurrentMerchant,
    uow: UoW,
    settings: SettingsDep,
    key: IdempotencyKey,
    request: Request,
    response: Response,
) -> MerchantPaymentOut:
    async def create() -> MerchantPaymentOut:
        payment = await PaymentService(uow, settings).request(
            merchant, str(body.customer_email), Money(body.amount), body.description
        )
        return MerchantPaymentOut.model_validate(payment)

    scope = f"merchant:{merchant.id}"
    stored = await run_once(request, response, uow, scope, key, body, create)
    return MerchantPaymentOut.model_validate(stored)


@router.get("")
async def list_payments(
    merchant: CurrentMerchant, uow: UoW, settings: SettingsDep
) -> list[MerchantPaymentOut]:
    payments = await PaymentService(uow, settings).list_for_merchant(merchant)
    return [MerchantPaymentOut.model_validate(payment) for payment in payments]


@router.get("/{payment_id}")
async def get_payment(
    payment_id: UUID, merchant: CurrentMerchant, uow: UoW, settings: SettingsDep
) -> MerchantPaymentOut:
    payment = await PaymentService(uow, settings).get_for_merchant(merchant, payment_id)
    return MerchantPaymentOut.model_validate(payment)


@router.post("/{payment_id}/capture")
async def capture(
    payment_id: UUID, merchant: CurrentMerchant, uow: UoW, settings: SettingsDep
) -> MerchantPaymentOut:
    payment = await PaymentService(uow, settings).capture(merchant, payment_id)
    await uow.commit()
    return MerchantPaymentOut.model_validate(payment)


@router.post("/{payment_id}/void")
async def void(
    payment_id: UUID, merchant: CurrentMerchant, uow: UoW, settings: SettingsDep
) -> MerchantPaymentOut:
    payment = await PaymentService(uow, settings).void(merchant, payment_id)
    await uow.commit()
    return MerchantPaymentOut.model_validate(payment)
