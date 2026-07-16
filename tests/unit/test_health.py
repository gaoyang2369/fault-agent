"""Health endpoint tests."""

import asyncio

from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app


def test_health_check_reports_api_liveness() -> None:
    async def request_health() -> tuple[int, object]:
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        return response.status_code, response.json()

    status_code, payload = asyncio.run(request_health())

    assert status_code == 200
    assert payload == {"status": "ok", "service": "fault-agent-api"}


def test_health_check_is_in_openapi_contract() -> None:
    schema = create_app().openapi()

    assert "/health" in schema["paths"]
