"""公开 telemetry HTTP 路由和组合根测试。"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.telemetry.application.ports import GuestTelemetryPolicy
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)


class HttpFixtureExecutor:
    """为 HTTP 集成测试提供两条源记录。"""

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        assert "FROM `real_data`" in sql
        assert parameters[:2] == ("G120电机1", "G120电机1")
        return [
            {"id": 1, "timestamp": "2026-01-14T06:00:00Z", "speed_actual": 10},
            {"id": 2, "timestamp": "2026-01-14T06:00:03Z", "speed_actual": 11},
        ]


def _service() -> TelemetryQueryService:
    repository = RealDataRepository(
        HttpFixtureExecutor(),
        source_timezone="UTC",
        create_time_filter_buffer_seconds=60,
        quality_settings=DataQualitySettings(
            nominal_interval_seconds=3,
            gap_warning_seconds=9,
            acceptable_completeness=0.95,
            insufficient_completeness=0.8,
        ),
    )
    return TelemetryQueryService(
        AssetSourceResolver(InMemoryAssetRepository.g120_fixture()),
        repository,
        policy=GuestTelemetryPolicy(
            frozenset({"asset-g120-1"}),
            now=lambda: datetime(2026, 1, 14, 6, 0, 6, tzinfo=UTC),
        ),
    )


def test_public_telemetry_route_uses_injected_composition_root() -> None:
    """验证 HTTP 只接受公开命令，并返回不含源定位信息的契约结果。"""

    async def request_telemetry() -> tuple[int, dict[str, object]]:
        app = create_app(_service())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/telemetry/queries",
                json={
                    "asset_code": "G120-1",
                    "time_range": {
                        "start": "2026-01-14T06:00:00Z",
                        "end": "2026-01-14T06:00:06Z",
                    },
                    "signal_codes": ["speed_actual"],
                    "aggregation": {"window_seconds": 3, "functions": ["AVG"]},
                    "max_points": 100,
                },
            )
        return response.status_code, response.json()

    status_code, payload = asyncio.run(request_telemetry())

    assert status_code == 200
    assert payload["asset_id"] == "asset-g120-1"
    assert "device_name" not in str(payload)
    assert "inverter_name" not in str(payload)


def test_telemetry_route_is_in_openapi_contract() -> None:
    schema = create_app(_service()).openapi()

    assert "/v1/telemetry/queries" in schema["paths"]
    assert "post" in schema["paths"]["/v1/telemetry/queries"]


def test_public_telemetry_route_enforces_guest_aggregation() -> None:
    """验证公开 HTTP 入口不能以游客身份请求原始点。"""

    async def request_raw_points() -> tuple[int, dict[str, object]]:
        transport = ASGITransport(app=create_app(_service()))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/telemetry/queries",
                json={
                    "asset_code": "G120-1",
                    "time_range": {
                        "start": "2026-01-14T06:00:00Z",
                        "end": "2026-01-14T06:00:06Z",
                    },
                    "signal_codes": ["speed_actual"],
                },
            )
        return response.status_code, response.json()

    status_code, payload = asyncio.run(request_raw_points())

    assert status_code == 403
    assert payload["error"]["code"] == "TELEMETRY_ACCESS_DENIED"  # type: ignore[index]
