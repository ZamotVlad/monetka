import asyncio
from uuid import uuid4

from httpx import AsyncClient

from tests.integration.conftest import Users


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


async def balance(client: AsyncClient, headers: dict[str, str]) -> int:
    response = await client.get("/api/v1/wallet", headers=headers)
    available: int = response.json()["available"]
    return available


async def test_transfer_moves_money_between_users(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    _, taras = await users.create("taras@example.com")

    response = await client.post(
        "/api/v1/transfers",
        json={"to_email": "taras@example.com", "amount": 2_500, "note": "for pizza"},
        headers=olena | key(),
    )
    assert response.status_code == 201
    assert response.json()["details"]["note"] == "for pizza"
    assert await balance(client, olena) == 7_500
    assert await balance(client, taras) == 2_500


async def test_transfer_errors(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com", balance=100)
    await users.create("taras@example.com")

    async def send(email: str, amount: int) -> str:
        response = await client.post(
            "/api/v1/transfers", json={"to_email": email, "amount": amount}, headers=olena | key()
        )
        code: str = response.json()["error"]["code"]
        return code

    assert await send("nobody@example.com", 10) == "not_found"
    assert await send("olena@example.com", 10) == "self_transfer"
    assert await send("taras@example.com", 101) == "insufficient_funds"
    assert await send("taras@example.com", 0) == "validation_error"


async def test_retry_with_same_key_is_replayed_not_repeated(
    client: AsyncClient, users: Users
) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    await users.create("taras@example.com")
    body = {"to_email": "taras@example.com", "amount": 1_000}
    headers = olena | key()

    first = await client.post("/api/v1/transfers", json=body, headers=headers)
    second = await client.post("/api/v1/transfers", json=body, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert second.headers["Idempotent-Replayed"] == "true"
    assert await balance(client, olena) == 9_000


async def test_same_key_with_different_body_is_rejected(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com", balance=10_000)
    await users.create("taras@example.com")
    headers = olena | key()
    await client.post(
        "/api/v1/transfers", json={"to_email": "taras@example.com", "amount": 1}, headers=headers
    )
    response = await client.post(
        "/api/v1/transfers", json={"to_email": "taras@example.com", "amount": 2}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_conflict"


async def test_missing_idempotency_key_is_a_validation_error(
    client: AsyncClient, users: Users
) -> None:
    _, olena = await users.create("olena@example.com", balance=100)
    response = await client.post(
        "/api/v1/withdrawals", json={"amount": 10, "card_last4": "4242"}, headers=olena
    )
    assert response.status_code == 422


async def test_hundred_parallel_withdrawals_never_overdraw(
    client: AsyncClient, users: Users
) -> None:
    """50 of 100 parallel requests fit the balance. Without row locks more would pass."""
    _, olena = await users.create("olena@example.com", balance=5_000)

    async def withdraw() -> int:
        response = await client.post(
            "/api/v1/withdrawals",
            json={"amount": 100, "card_last4": "4242"},
            headers=olena | key(),
        )
        return response.status_code

    statuses = await asyncio.gather(*(withdraw() for _ in range(100)))

    assert statuses.count(201) == 50
    assert statuses.count(422) == 50
    assert await balance(client, olena) == 0


async def test_parallel_retries_of_one_request_run_once(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com", balance=5_000)
    headers = olena | key()

    async def withdraw() -> int:
        response = await client.post(
            "/api/v1/withdrawals", json={"amount": 100, "card_last4": "4242"}, headers=headers
        )
        return response.status_code

    statuses = await asyncio.gather(*(withdraw() for _ in range(20)))

    assert set(statuses) == {201}
    assert await balance(client, olena) == 4_900


async def test_opposite_transfers_do_not_deadlock(client: AsyncClient, users: Users) -> None:
    _, olena = await users.create("olena@example.com", balance=100_000)
    _, taras = await users.create("taras@example.com", balance=100_000)

    async def send(headers: dict[str, str], to: str) -> int:
        response = await client.post(
            "/api/v1/transfers", json={"to_email": to, "amount": 10}, headers=headers | key()
        )
        return response.status_code

    jobs = [send(olena, "taras@example.com") for _ in range(25)]
    jobs += [send(taras, "olena@example.com") for _ in range(25)]
    statuses = await asyncio.wait_for(asyncio.gather(*jobs), timeout=30)

    assert set(statuses) == {201}
    assert await balance(client, olena) + await balance(client, taras) == 200_000
