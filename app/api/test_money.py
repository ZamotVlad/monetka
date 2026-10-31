from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SettingsDep, UoW
from app.api.idempotency import IdempotencyKey, run_once
from app.api.rate_limit import money_limit
from app.api.schemas import TransactionOut
from app.domain.errors import NotFound
from app.domain.money import Money
from app.services.wallet import WalletService

router = APIRouter(tags=["test money"])

TEST_TOP_UP = Money(100_000)


class ClientConfig(BaseModel):
    test_money: bool


class TestMoneyIn(BaseModel):
    pass


@router.get("/config")
async def client_config(settings: SettingsDep) -> ClientConfig:
    """What the web app should show; for now only whether the test money button exists."""
    return ClientConfig(test_money=settings.test_money_enabled)


@router.post(
    "/test-money", status_code=status.HTTP_201_CREATED, dependencies=[Depends(money_limit)]
)
async def add_test_money(
    user: CurrentUser,
    uow: UoW,
    settings: SettingsDep,
    key: IdempotencyKey,
    request: Request,
    response: Response,
) -> TransactionOut:
    """Adds 1 000 ₴ of play money. Answers 404 when disabled, as if it did not exist."""
    if not settings.test_money_enabled:
        raise NotFound("Not found")

    async def add() -> TransactionOut:
        transaction = await WalletService(uow).add_test_money(user, TEST_TOP_UP)
        return TransactionOut.model_validate(transaction)

    stored = await run_once(request, response, uow, str(user.id), key, TestMoneyIn(), add)
    return TransactionOut.model_validate(stored)
