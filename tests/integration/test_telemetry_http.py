"""公开 telemetry HTTP 路由和组合根测试。"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.iam.application.policy import IamAuthorizationPolicy
from modules.iam.domain.models import IamPolicyConfig, TrustedPrincipal
from modules.iam.infrastructure.authentication import InMemoryBearerAuthenticationBackend
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)
from shared.context import Role


class HttpFixtureExecutor:
    """为 HTTP 集成测试提供两条源记录。"""

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        assert "FROM `real_data`" in sql
        assert parameters[:2] == ("G120电机1", "G120电机1")
        return [
            {"id": 1, "timestamp": "2026-01-14T06:00:00Z", "speed_actual": 10},
            {"id": 2, "timestamp": "2026-01-14T06:00:03Z", "speed_actual": 11},
        ]


def _service(policy: IamAuthorizationPolicy | None = None) -> TelemetryQueryService:
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
        policy=policy
        or IamAuthorizationPolicy(
            IamPolicyConfig(guest_visible_asset_ids=frozenset({"asset-g120-1"})),
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
                    "aggregation": {"window_seconds": 60, "functions": ["AVG"]},
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


def test_http_authentication_boundary_supplies_engineer_identity_and_scope() -> None:
    """验证 HTTP payload 不能自报身份，Bearer 认证结果决定工程师资产范围。"""

    async def request_as_engineer(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        principal = TrustedPrincipal(
            user_id="engineer-1",
            roles=frozenset({Role.ENGINEER}),
            authenticated_at=datetime(2026, 1, 14, 6, tzinfo=UTC),
        )
        authentication = InMemoryBearerAuthenticationBackend({"engineer-token": principal})
        iam = IamAuthorizationPolicy(
            IamPolicyConfig(engineer_asset_assignments={"engineer-1": frozenset({"asset-g120-1"})})
        )
        app = create_app(
            _service(iam),
            authentication_backend=authentication,
            iam_policy=iam,
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/telemetry/queries",
                headers={"Authorization": "Bearer engineer-token"},
                json=payload,
            )
        return response.status_code, response.json()

    base: dict[str, object] = {
        "asset_code": "G120-1",
        "time_range": {
            "start": "2026-01-14T06:00:00Z",
            "end": "2026-01-14T06:00:06Z",
        },
        "signal_codes": ["speed_actual"],
    }
    status_code, _ = asyncio.run(request_as_engineer(base))
    spoofed_status, _ = asyncio.run(
        request_as_engineer({**base, "role": "ADMIN", "user_id": "attacker"})
    )

    assert status_code == 200
    assert spoofed_status == 422


def test_invalid_bearer_token_returns_unauthorized() -> None:
    """验证无效认证凭据在调用应用服务前返回 401。"""

    async def request_with_invalid_token() -> tuple[int, dict[str, object]]:
        app = create_app(
            _service(),
            authentication_backend=InMemoryBearerAuthenticationBackend({}),
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/telemetry/queries",
                headers={"Authorization": "Bearer invalid"},
                json={
                    "asset_code": "G120-1",
                    "time_range": {
                        "start": "2026-01-14T06:00:00Z",
                        "end": "2026-01-14T06:00:06Z",
                    },
                    "signal_codes": ["speed_actual"],
                    "aggregation": {"window_seconds": 60, "functions": ["AVG"]},
                },
            )
        return response.status_code, response.json()

    status_code, payload = asyncio.run(request_with_invalid_token())
    assert status_code == 401
    assert payload["error"]["code"] == "AUTHENTICATION_REQUIRED"  # type: ignore[index]
