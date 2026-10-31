import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from app.db.uow import UnitOfWork
from app.domain.ledger import PSP_ACCOUNT_ID, TransactionKind, move
from app.domain.money import Money
from app.main import create_app
from app.services.ledger import LedgerService

# Ryuk is the testcontainers reaper; the containers are stopped by the fixture anyway
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine", driver="asyncpg").start()
    except Exception as error:  # docker missing or not running
        pytest.skip(f"PostgreSQL container unavailable: {error}")
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    # Alembic's env.py runs its own event loop, so it gets a thread of its own
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_database(engine: AsyncEngine) -> None:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await connection.execute(
            text("INSERT INTO accounts (id, kind, allow_negative) VALUES (:id, 'system', true)"),
            {"id": PSP_ACCOUNT_ID},
        )


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(environment="test", database_url=database_url, bcrypt_rounds=4)


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def app(
    settings: Settings, engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> FastAPI:
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = FakeAsyncRedis(decode_responses=True)
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


class Users:
    """Shortcuts for tests that need signed-in users with money."""

    def __init__(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._client = client
        self._session_factory = session_factory

    async def create(self, email: str, balance: int = 0) -> tuple[UUID, dict[str, str]]:
        credentials = {"email": email, "password": "correct-horse"}
        response = await self._client.post("/api/v1/auth/register", json=credentials)
        assert response.status_code == 201, response.text
        user_id = UUID(response.json()["id"])
        token = (await self._client.post("/api/v1/auth/login", json=credentials)).json()
        if balance:
            await self.fund(user_id, balance)
        return user_id, {"Authorization": f"Bearer {token['access_token']}"}

    async def fund(self, user_id: UUID, amount: int) -> None:
        async with UnitOfWork(self._session_factory) as uow:
            wallet = await uow.accounts.wallet_of(user_id)
            postings = move(PSP_ACCOUNT_ID, wallet.id, Money(amount))
            await LedgerService(uow).post(TransactionKind.DEPOSIT, postings)
            await uow.commit()


@pytest.fixture
def users(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> Users:
    return Users(client, session_factory)
