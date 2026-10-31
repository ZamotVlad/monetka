from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.realtime import Hub


@pytest.fixture
def app() -> FastAPI:
    app = create_app(Settings(environment="test", kafka_enabled=False))
    app.state.hub = Hub()
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # ASGITransport does not run the lifespan, so these tests need no database or Redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
