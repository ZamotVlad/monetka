import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from httpx import AsyncClient

from app.config import Settings
from psp_mock.signing import decode_checkout, sign
from tests.integration.conftest import Users


async def start_deposit(client: AsyncClient, headers: dict[str, str], amount: int) -> str:
    response = await client.post(
        "/api/v1/deposits",
        json={"amount": amount},
        headers=headers | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    deposit_id: str = response.json()["id"]
    return deposit_id


async def send_webhook(
    client: AsyncClient,
    settings: Settings,
    event: dict[str, Any],
    sent_at: int | None = None,
    secret: str | None = None,
) -> Any:
    body = json.dumps(event).encode()
    timestamp = str(sent_at or int(time.time()))
    signature = sign(secret or settings.psp_secret, timestamp.encode() + b"." + body)
    return await client.post(
        "/api/v1/webhooks/psp",
        content=body,
        headers={"X-Psp-Timestamp": timestamp, "X-Psp-Signature": signature},
    )


def event(deposit_id: str, amount: int, status: str = "succeeded") -> dict[str, Any]:
    return {
        "event_id": f"evt_{uuid4().hex}",
        "deposit_id": deposit_id,
        "status": status,
        "amount": amount,
        "card_last4": "4242",
    }


async def available(client: AsyncClient, headers: dict[str, str]) -> int:
    value: int = (await client.get("/api/v1/wallet", headers=headers)).json()["available"]
    return value


async def test_checkout_link_is_signed_for_the_provider(
    client: AsyncClient, users: Users, settings: Settings
) -> None:
    _, olena = await users.create("olena@example.com")
    response = await client.post(
        "/api/v1/deposits",
        json={"amount": 50_000},
        headers=olena | {"Idempotency-Key": str(uuid4())},
    )
    query = parse_qs(urlparse(response.json()["checkout_url"]).query)
    params = decode_checkout(settings.psp_secret, query["data"][0], query["signature"][0])
    assert params is not None
    assert params["amount"] == 50_000
    assert params["deposit_id"] == response.json()["id"]


async def test_successful_webhook_credits_the_wallet_once(
    client: AsyncClient, users: Users, settings: Settings
) -> None:
    _, olena = await users.create("olena@example.com")
    deposit_id = await start_deposit(client, olena, 50_000)
    payload = event(deposit_id, 50_000)

    first = await send_webhook(client, settings, payload)
    again = await send_webhook(client, settings, payload)

    assert first.json() == {"result": "processed"}
    assert again.json() == {"result": "duplicate"}
    assert await available(client, olena) == 50_000
    deposit = await client.get(f"/api/v1/deposits/{deposit_id}", headers=olena)
    assert deposit.json()["status"] == "succeeded"


async def test_late_failure_does_not_undo_a_top_up(
    client: AsyncClient, users: Users, settings: Settings
) -> None:
    _, olena = await users.create("olena@example.com")
    deposit_id = await start_deposit(client, olena, 50_000)

    await send_webhook(client, settings, event(deposit_id, 50_000))
    late = await send_webhook(client, settings, event(deposit_id, 50_000, "failed"))

    assert late.json() == {"result": "already_final"}
    assert await available(client, olena) == 50_000


async def test_amount_mismatch_fails_the_deposit(
    client: AsyncClient, users: Users, settings: Settings
) -> None:
    _, olena = await users.create("olena@example.com")
    deposit_id = await start_deposit(client, olena, 50_000)

    response = await send_webhook(client, settings, event(deposit_id, 99_999_999))

    assert response.json() == {"result": "amount_mismatch"}
    assert await available(client, olena) == 0


async def test_forged_and_replayed_webhooks_are_rejected(
    client: AsyncClient, users: Users, settings: Settings
) -> None:
    _, olena = await users.create("olena@example.com")
    deposit_id = await start_deposit(client, olena, 50_000)

    forged = await send_webhook(client, settings, event(deposit_id, 50_000), secret="guess")
    replayed = await send_webhook(
        client, settings, event(deposit_id, 50_000), sent_at=int(time.time()) - 3600
    )

    assert forged.status_code == replayed.status_code == 401
    assert await available(client, olena) == 0
