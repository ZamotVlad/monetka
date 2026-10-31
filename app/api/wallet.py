from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, UoW
from app.api.schemas import BalanceOut, HistoryItem, HistoryPage
from app.services.wallet import WalletService

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("")
async def balance(user: CurrentUser, uow: UoW) -> BalanceOut:
    result = await WalletService(uow).balance(user.id)
    return BalanceOut(available=result.available, held=result.held, total=result.total)


@router.get("/history")
async def history(
    user: CurrentUser,
    uow: UoW,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: int | None = None,
) -> HistoryPage:
    rows = await WalletService(uow).history(user.id, limit, before)
    items = [HistoryItem.model_validate(row) for row in rows]
    next_before = items[-1].id if len(items) == limit else None
    return HistoryPage(items=items, next_before=next_before)
