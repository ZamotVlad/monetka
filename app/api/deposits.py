import time
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.api.deps import CurrentUser, SettingsDep, UoW
from app.api.idempotency import IdempotencyKey, run_once
from app.api.rate_limit import money_limit
from app.api.schemas import DepositIn, DepositOut, ProviderEventIn
from app.domain.money import Money
from app.integrations import psp
from app.observability import WEBHOOKS
from app.services.deposits import DepositService, DepositStatus, ProviderEvent

router = APIRouter(tags=["deposits"])


@router.post("/deposits", status_code=status.HTTP_201_CREATED, dependencies=[Depends(money_limit)])
async def start_deposit(
    body: DepositIn,
    user: CurrentUser,
    uow: UoW,
    settings: SettingsDep,
    key: IdempotencyKey,
    request: Request,
    response: Response,
) -> DepositOut:
    """Creates a pending top-up and returns the provider page to pay on."""

    async def start() -> DepositOut:
        deposit, checkout_url = await DepositService(uow, settings).start(user, Money(body.amount))
        result = DepositOut.model_validate(deposit)
        result.checkout_url = checkout_url
        return result

    stored = await run_once(request, response, uow, str(user.id), key, body, start)
    return DepositOut.model_validate(stored)


@router.get("/deposits/{deposit_id}")
async def get_deposit(
    deposit_id: UUID, user: CurrentUser, uow: UoW, settings: SettingsDep
) -> DepositOut:
    deposit = await DepositService(uow, settings).get(user, deposit_id)
    return DepositOut.model_validate(deposit)


@router.post("/webhooks/psp", include_in_schema=False)
async def provider_webhook(
    request: Request,
    uow: UoW,
    settings: SettingsDep,
    timestamp: str = Header(alias="X-Psp-Timestamp"),
    signature: str = Header(alias="X-Psp-Signature"),
) -> dict[str, str]:
    # The signature covers the exact bytes, so check it before parsing anything
    body = await request.body()
    psp.verify_webhook(
        settings.psp_secret,
        body,
        timestamp,
        signature,
        now=time.time(),
        tolerance=settings.webhook_tolerance_seconds,
    )
    event = ProviderEventIn.model_validate_json(body)
    result = await DepositService(uow, settings).handle(
        ProviderEvent(
            event_id=event.event_id,
            deposit_id=event.deposit_id,
            status=DepositStatus(event.status),
            amount=event.amount,
            card_last4=event.card_last4,
        )
    )
    await uow.commit()
    WEBHOOKS.labels(result).inc()
    return {"result": result}
