from httpx import AsyncClient

from tests.integration.conftest import Users

CREDENTIALS = {"email": "Olena@Example.com", "password": "correct-horse"}


async def test_register_login_and_me(client: AsyncClient) -> None:
    registered = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    assert registered.status_code == 201
    assert registered.json()["email"] == "olena@example.com"

    token = (await client.post("/api/v1/auth/login", json=CREDENTIALS)).json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "olena@example.com"


async def test_duplicate_email_is_rejected(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=CREDENTIALS)
    response = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_wrong_password_and_unknown_email_look_the_same(
    client: AsyncClient, users: Users
) -> None:
    await users.create("olena@example.com")
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "olena@example.com", "password": "wrong-pass"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_protected_route_needs_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/wallet")).status_code == 401
    bad = await client.get("/api/v1/wallet", headers={"Authorization": "Bearer nonsense"})
    assert bad.json()["error"]["code"] == "invalid_credentials"


async def test_short_password_is_a_validation_error(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": "a@example.com", "password": "short"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
