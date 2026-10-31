from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.storage import MemoryStorage
from app.services.statements import month_bounds, previous_period, safe_cell
from app.workers.jobs import monthly_statements
from tests.integration.conftest import Users

THIS_MONTH = datetime.now(UTC).strftime("%Y-%m")


def test_month_bounds_cross_the_year() -> None:
    start, end = month_bounds("2026-12")
    assert (start.month, end.year, end.month) == (12, 2027, 1)
    assert previous_period(datetime(2027, 1, 15, tzinfo=UTC)) == "2026-12"


async def test_user_generates_and_lists_a_statement(
    app: FastAPI, client: AsyncClient, users: Users
) -> None:
    _, olena = await users.create("olena@example.com", balance=12_345)

    created = await client.post("/api/v1/statements", json={"period": THIS_MONTH}, headers=olena)
    assert created.status_code == 201
    assert created.json()["rows"] == 1

    listed = (await client.get("/api/v1/statements", headers=olena)).json()
    assert [s["period"] for s in listed] == [THIS_MONTH]

    storage: MemoryStorage = app.state.storage
    body, content_type = next(iter(storage.files.values()))
    assert content_type == "text/csv"
    assert "deposit" in body.decode()
    assert "123.45" in body.decode()


async def test_regenerating_replaces_the_statement(client: AsyncClient, users: Users) -> None:
    olena_id, olena = await users.create("olena@example.com", balance=100)
    await client.post("/api/v1/statements", json={"period": THIS_MONTH}, headers=olena)
    await users.fund(olena_id, 200)
    await client.post("/api/v1/statements", json={"period": THIS_MONTH}, headers=olena)

    listed = (await client.get("/api/v1/statements", headers=olena)).json()
    assert [(s["period"], s["rows"]) for s in listed] == [(THIS_MONTH, 2)]


async def test_bad_period_is_rejected(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com")
    response = await client.post("/api/v1/statements", json={"period": "2026-13"}, headers=olena)
    assert response.status_code == 422


async def test_monthly_job_skips_users_without_activity(
    users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await users.create("olena@example.com", balance=100)
    # All activity is in the current month, so last month has nothing to report
    assert await monthly_statements(session_factory, MemoryStorage()) == 0


def test_cells_that_excel_would_run_as_formulas_are_escaped() -> None:
    assert safe_cell('=HYPERLINK("http://evil")') == '\'=HYPERLINK("http://evil")'
    assert safe_cell("note=for pizza") == "note=for pizza"
