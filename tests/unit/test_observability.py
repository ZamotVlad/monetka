from httpx import AsyncClient


async def test_request_id_is_returned_and_kept(client: AsyncClient) -> None:
    generated = await client.get("/api/v1/health/live")
    assert len(generated.headers["x-request-id"]) == 32

    kept = await client.get("/api/v1/health/live", headers={"X-Request-ID": "trace-123"})
    assert kept.headers["x-request-id"] == "trace-123"


async def test_metrics_use_route_templates(client: AsyncClient) -> None:
    await client.get("/api/v1/health/live")
    body = (await client.get("/metrics")).text
    assert 'route="/api/v1/health/live"' in body
    assert "monetka_http_request_seconds_bucket" in body
