from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import CurrentUser, UoW
from app.api.idempotency import IdempotencyKey, run_once
from app.api.rate_limit import money_limit
from app.api.schemas import TransactionOut, TransferIn, WithdrawalIn
from app.domain.money import Money
from app.services.wallet import WalletService

router = APIRouter(tags=["wallet"], dependencies=[Depends(money_limit)])


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
async def create_transfer(
    body: TransferIn,
    user: CurrentUser,
    uow: UoW,
    key: IdempotencyKey,
    request: Request,
    response: Response,
) -> TransactionOut:
    async def transfer() -> TransactionOut:
        transaction = await WalletService(uow).transfer(
            user, str(body.to_email), Money(body.amount), body.note
        )
        return TransactionOut.model_validate(transaction)

    stored = await run_once(request, response, uow, str(user.id), key, body, transfer)
    return TransactionOut.model_validate(stored)


@router.post("/withdrawals", status_code=status.HTTP_201_CREATED)
async def create_withdrawal(
    body: WithdrawalIn,
    user: CurrentUser,
    uow: UoW,
    key: IdempotencyKey,
    request: Request,
    response: Response,
) -> TransactionOut:
    async def withdraw() -> TransactionOut:
        transaction = await WalletService(uow).withdraw(user, Money(body.amount), body.card_last4)
        return TransactionOut.model_validate(transaction)

    stored = await run_once(request, response, uow, str(user.id), key, body, withdraw)
    return TransactionOut.model_validate(stored)
