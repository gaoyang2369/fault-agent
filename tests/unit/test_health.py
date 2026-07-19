"""健康检查端点测试。"""

import asyncio

from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app


def test_health_check_reports_api_liveness() -> None:
    """验证健康检查报告 API 存活且响应契约稳定。"""

    async def request_health() -> tuple[int, object]:
        """通过 ASGI 传输调用健康端点并返回状态码与响应体。"""

        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        return response.status_code, response.json()

    status_code, payload = asyncio.run(request_health())

    assert status_code == 200
    assert payload == {"status": "ok", "service": "fault-agent-api"}


def test_health_check_is_in_openapi_contract() -> None:
    """验证健康检查端点已注册到 OpenAPI 契约。"""

    schema = create_app().openapi()

    assert "/health" in schema["paths"]
