import asyncio
from datetime import timedelta
from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import Payment
from app.services.payments import utcnow
from app.workers.jobs import expire_payments
from tests.integration.conftest import Users


async def wallet(client: AsyncClient, headers: dict[str, str]) -> dict[str, int]:
    body: dict[str, int] = (await client.get("/api/v1/wallet", headers=headers)).json()
    return body


async def request_payment(
    client: AsyncClient, merchant: dict[str, str], amount: int = 8_600
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/merchant/payments",
        json={"customer_email": "olena@example.com", "amount": amount, "description": "Latte"},
        headers=merchant | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_full_payment_flow(
    client: AsyncClient, users: Users, merchant: dict[str, str]
) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    payment = await request_payment(client, merchant)

    pending = (await client.get("/api/v1/payments?status=pending", headers=olena)).json()
    assert [p["merchant_name"] for p in pending] == ["Coffee Grain"]

    confirmed = await client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=olena)
    assert confirmed.json()["status"] == "authorized"
    assert await wallet(client, olena) == {
        "available": 1_400,
        "held": 8_600,
        "total": 10_000,
        "currency": "UAH",
    }

    captured = await client.post(
        f"/api/v1/merchant/payments/{payment['id']}/capture", headers=merchant
    )
    assert captured.json()["status"] == "captured"
    assert (await wallet(client, olena))["total"] == 1_400

    history = (await client.get("/api/v1/wallet/history", headers=olena)).json()["items"]
    assert [i["kind"] for i in history] == ["capture", "hold", "deposit"]
    assert history[0]["details"]["merchant"] == "Coffee Grain"


async def test_void_returns_the_reserve(
    client: AsyncClient, users: Users, merchant: dict[str, str]
) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    payment = await request_payment(client, merchant)
    await client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=olena)

    voided = await client.post(f"/api/v1/merchant/payments/{payment['id']}/void", headers=merchant)

    assert voided.json()["status"] == "voided"
    assert (await wallet(client, olena))["available"] == 10_000


async def test_confirm_without_money_keeps_request_pending(
    client: AsyncClient, users: Users, merchant: dict[str, str]
) -> None:
    _, olena = await users.create("olena@example.com", balance=100)
    payment = await request_payment(client, merchant)

    response = await client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=olena)

    assert response.json()["error"]["code"] == "insufficient_funds"
    status = await client.get(f"/api/v1/merchant/payments/{payment['id']}", headers=merchant)
    assert status.json()["status"] == "pending"


async def test_wrong_order_is_refused(
    client: AsyncClient, users: Users, merchant: dict[str, str]
) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    payment = await request_payment(client, merchant)

    capture = await client.post(
        f"/api/v1/merchant/payments/{payment['id']}/capture", headers=merchant
    )
    assert capture.status_code == 409

    await client.post(f"/api/v1/payments/{payment['id']}/decline", headers=olena)
    confirm = await client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=olena)
    assert confirm.json()["error"]["code"] == "invalid_transition"


async def test_strangers_cannot_touch_a_payment(
    client: AsyncClient, users: Users, merchant: dict[str, str]
) -> None:
    await users.create("olena@example.com", balance=10_000)
    _, taras = await users.create("taras@example.com")
    payment = await request_payment(client, merchant)

    response = await client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=taras)
    assert response.status_code == 404

    unknown = await client.get("/api/v1/merchant/payments", headers={"X-API-Key": "mk_fake"})
    assert unknown.status_code == 401


async def test_capture_and_void_race_has_one_winner(
    client: AsyncClient, users: Users, merchant: dict[str, str]
) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    payment = await request_payment(client, merchant)
    await client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=olena)

    capture, void = await asyncio.gather(
        client.post(f"/api/v1/merchant/payments/{payment['id']}/capture", headers=merchant),
        client.post(f"/api/v1/merchant/payments/{payment['id']}/void", headers=merchant),
    )

    assert sorted([capture.status_code, void.status_code]) == [200, 409]
    balance = await wallet(client, olena)
    assert balance["held"] == 0
    assert balance["available"] in {1_400, 10_000}


async def test_worker_expires_old_requests_and_releases_holds(
    client: AsyncClient,
    users: Users,
    merchant: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    unanswered = await request_payment(client, merchant, amount=500)
    held = await request_payment(client, merchant, amount=8_600)
    await client.post(f"/api/v1/payments/{held['id']}/confirm", headers=olena)

    async with session_factory() as session:
        await session.execute(update(Payment).values(expires_at=utcnow() - timedelta(seconds=1)))
        await session.commit()

    assert await expire_payments(session_factory, settings) == 2

    for payment in (unanswered, held):
        response = await client.get(f"/api/v1/merchant/payments/{payment['id']}", headers=merchant)
        assert response.json()["status"] == "expired"
    assert (await wallet(client, olena))["available"] == 10_000
