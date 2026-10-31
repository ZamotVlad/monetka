from httpx import AsyncClient


async def test_frontend_is_served_next_to_the_api(client: AsyncClient) -> None:
    index = await client.get("/")
    assert index.status_code == 200
    assert 'src="assets/js/auth.js"' in index.text

    script = await client.get("/assets/js/api.js")
    assert script.headers["content-type"].startswith("text/javascript")


async def test_api_routes_win_over_static_files(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.json() == {"status": "ok"}
