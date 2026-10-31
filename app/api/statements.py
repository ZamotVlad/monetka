from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, UoW
from app.api.schemas import StatementIn, StatementOut
from app.integrations.storage import FileStorage
from app.services.statements import StatementService

router = APIRouter(prefix="/statements", tags=["statements"])


def storage_of(request: Request) -> FileStorage:
    storage: FileStorage = request.app.state.storage
    return storage


@router.get("")
async def list_statements(user: CurrentUser, uow: UoW, request: Request) -> list[StatementOut]:
    statements = await StatementService(uow, storage_of(request)).list_with_links(user.id)
    return [
        StatementOut(period=s.period, rows=s.rows, created_at=s.created_at, download_url=url)
        for s, url in statements
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def generate_statement(
    body: StatementIn, user: CurrentUser, uow: UoW, request: Request
) -> StatementOut:
    """Builds the month's CSV now; the worker also does it on the 1st for last month."""
    storage = storage_of(request)
    statement = await StatementService(uow, storage).generate(user.id, body.period)
    await uow.commit()
    return StatementOut(
        period=statement.period,
        rows=statement.rows,
        created_at=statement.created_at,
        download_url=await storage.download_url(statement.object_key),
    )
