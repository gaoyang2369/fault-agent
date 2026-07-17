"""Public asset-based flow hides the real_data locator."""

import asyncio
from collections.abc import Sequence

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.infrastructure.legacy_backend import LegacyRealDataBackend
from modules.telemetry.models import DataQualitySettings
from modules.telemetry.repository import RealDataRepository, Row
from modules.telemetry.service import TelemetryQueryService as LegacyTelemetryQueryService
from shared.context import RequestContext, RequestSource, Role


class FixtureExecutor:
    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        del sql, parameters
        return [
            {
                "id": 1,
                "timestamp": "2026-01-14T06:00:00Z",
                "device_name": "G120电机1",
                "inverter_name": "G120电机1",
                "speed_actual": 10,
            }
        ]


def test_public_flow_uses_asset_and_does_not_return_locator_fields() -> None:
    assets = InMemoryAssetRepository.g120_fixture()
    legacy = LegacyTelemetryQueryService(
        RealDataRepository(
            FixtureExecutor(), source_timezone="UTC", create_time_filter_buffer_seconds=60
        ),
        quality_settings=DataQualitySettings(
            nominal_interval_seconds=3,
            gap_warning_seconds=9,
            acceptable_completeness=0.95,
            insufficient_completeness=0.8,
        ),
    )
    service = TelemetryQueryService(AssetSourceResolver(assets), LegacyRealDataBackend(legacy))

    result = asyncio.run(
        service.query(
            TelemetryQueryCommand.model_validate(
                {
                    "asset_code": "G120-1",
                    "time_range": {
                        "start": "2026-01-14T06:00:00Z",
                        "end": "2026-01-14T06:00:03Z",
                    },
                    "signal_codes": ["speed_actual"],
                }
            ),
            RequestContext(
                request_id="request-1",
                trace_id="trace-1",
                user_id="engineer-1",
                roles=frozenset({Role.ENGINEER}),
                request_source=RequestSource.HTTP,
            ),
        )
    )

    serialized = result.model_dump_json()
    assert result.asset_id == "asset-g120-1"
    assert "device_name" not in serialized
    assert "inverter_name" not in serialized
