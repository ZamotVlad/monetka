from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User
from tests.integration.conftest import Users


async def make_operator(
    session_factory: async_sessionmaker[AsyncSession], users: Users
) -> dict[str, str]:
    operator_id, headers = await users.create("ops@example.com")
    async with session_factory() as session:
        await session.execute(update(User).where(User.id == operator_id).values(is_operator=True))
        await session.commit()
    return headers


async def test_operator_sees_balanced_books(
    client: AsyncClient, users: Users, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    operator = await make_operator(session_factory, users)
    _, olena = await users.create("olena@example.com", balance=5_000)
    await users.create("taras@example.com")
    await client.post(
        "/api/v1/transfers",
        json={"to_email": "taras@example.com", "amount": 1_000},
        headers=olena | {"Idempotency-Key": str(uuid4())},
    )

    overview = (await client.get("/api/v1/ops/overview", headers=operator)).json()
    assert overview["users"] == 3
    assert overview["books_total"] == 0
    assert overview["balances"]["wallet"] == 5_000

    journal = (await client.get("/api/v1/ops/journal", headers=operator)).json()
    assert [entry["kind"] for entry in journal] == ["transfer", "deposit"]
    transfer = journal[0]
    assert sum(line["amount"] for line in transfer["lines"]) == 0
    assert {line["owner"] for line in transfer["lines"]} == {
        "olena@example.com",
        "taras@example.com",
    }
    assert "card provider" in {line["owner"] for line in journal[1]["lines"]}

    run = (await client.post("/api/v1/ops/reconciliation", headers=operator)).json()
    assert run["ok"] is True


async def test_regular_users_cannot_open_ops(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com")
    response = await client.get("/api/v1/ops/overview", headers=olena)
    assert response.status_code == 403
