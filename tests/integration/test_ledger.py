import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Account
from app.db.uow import UnitOfWork
from app.domain.errors import InsufficientFunds
from app.domain.ledger import TransactionKind, move
from app.domain.money import Money
from app.services.ledger import LedgerService
from tests.integration.conftest import Users


async def test_new_user_has_empty_wallet(client: AsyncClient, users: Users) -> None:
    _, headers = await users.create("olena@example.com")
    response = await client.get("/api/v1/wallet", headers=headers)
    assert response.json() == {"available": 0, "held": 0, "total": 0, "currency": "UAH"}


async def test_posting_moves_money_and_shows_in_history(client: AsyncClient, users: Users) -> None:
    _, headers = await users.create("olena@example.com", balance=10_000)
    assert (await client.get("/api/v1/wallet", headers=headers)).json()["available"] == 10_000

    history = (await client.get("/api/v1/wallet/history", headers=headers)).json()
    assert [(i["kind"], i["wallet_delta"]) for i in history["items"]] == [("deposit", 10_000)]


async def test_overdraft_is_refused_and_nothing_changes(
    session_factory: async_sessionmaker[AsyncSession], users: Users
) -> None:
    olena, _ = await users.create("olena@example.com", balance=100)
    taras, _ = await users.create("taras@example.com")
    async with UnitOfWork(session_factory) as uow:
        source = await uow.accounts.wallet_of(olena)
        target = await uow.accounts.wallet_of(taras)
        with pytest.raises(InsufficientFunds):
            await LedgerService(uow).post(
                TransactionKind.TRANSFER, move(source.id, target.id, Money(101))
            )
    async with UnitOfWork(session_factory) as uow:
        assert (await uow.accounts.wallet_of(olena)).balance == 100


async def test_database_refuses_negative_wallet_even_if_code_is_wrong(
    session_factory: async_sessionmaker[AsyncSession], users: Users
) -> None:
    olena, _ = await users.create("olena@example.com")
    async with UnitOfWork(session_factory) as uow:
        with pytest.raises(IntegrityError):
            await uow.session.execute(
                update(Account).where(Account.user_id == olena).values(balance=-1)
            )
