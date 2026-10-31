from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError

from app.config import Settings
from tests.integration.conftest import Users


async def test_button_is_hidden_and_endpoint_absent_by_default(
    client: AsyncClient, users: Users
) -> None:
    _, olena = await users.create("olena@example.com")
    assert (await client.get("/api/v1/config")).json() == {"test_money": False}
    response = await client.post(
        "/api/v1/test-money", headers=olena | {"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 404


async def test_test_money_is_a_balanced_posting(
    app: FastAPI, client: AsyncClient, users: Users
) -> None:
    app.state.settings.test_money_enabled = True
    _, olena = await users.create("olena@example.com")
    headers = olena | {"Idempotency-Key": str(uuid4())}

    first = await client.post("/api/v1/test-money", headers=headers)
    retry = await client.post("/api/v1/test-money", headers=headers)

    assert first.status_code == retry.status_code == 201
    assert first.json()["details"] == {"source": "test"}
    wallet = (await client.get("/api/v1/wallet", headers=olena)).json()
    assert wallet["available"] == 100_000


def test_production_refuses_test_money() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret="x" * 40,
            psp_secret="y" * 40,
            test_money_enabled=True,
        )
