from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import Operator, UoW
from app.api.schemas import JournalEntryOut, OverviewOut, ReconciliationOut
from app.db.uow import UnitOfWork
from app.services.ops import OpsService
from app.services.reconciliation import ReconciliationService

router = APIRouter(prefix="/ops", tags=["operator"])


@router.get("/overview")
async def overview(operator: Operator, uow: UoW, request: Request) -> OverviewOut:
    result = OverviewOut.model_validate(await OpsService(uow).overview())
    result.online = request.app.state.hub.online
    return result


@router.get("/journal")
async def journal(
    operator: Operator,
    uow: UoW,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: int | None = None,
) -> list[JournalEntryOut]:
    entries = await OpsService(uow).journal(limit, before)
    return [JournalEntryOut.model_validate(entry) for entry in entries]


@router.get("/reconciliation")
async def reconciliation_runs(operator: Operator, uow: UoW) -> list[ReconciliationOut]:
    return [ReconciliationOut.model_validate(run) for run in await OpsService(uow).runs(20)]


@router.post("/reconciliation")
async def reconcile_now(operator: Operator, request: Request) -> ReconciliationOut:
    # A fresh transaction: the request's one already ran a query to load the operator,
    # and the isolation level can only be chosen before the first query
    async with UnitOfWork(request.app.state.session_factory) as uow:
        run = await ReconciliationService(uow).run()
        await uow.commit()
    return ReconciliationOut.model_validate(run)
