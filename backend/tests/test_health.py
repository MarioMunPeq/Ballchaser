"""Tests del endpoint de salud."""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_includes_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert "X-Request-Id" in response.headers


async def test_health_echoes_incoming_request_id(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-Id": "abc123"})

    assert response.headers["X-Request-Id"] == "abc123"
