"""验证基于公开资产的流程会隐藏 real_data 定位信息。"""

import asyncio
from collections.abc import Sequence

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.iam.application.policy import IamAuthorizationPolicy
from modules.iam.domain.models import IamPolicyConfig
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)
from shared.context import RequestContext, RequestSource, Role


class FixtureExecutor:
    """为公开遥测集成流程提供固定源记录的查询执行器。"""

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        """忽略固定查询文本并返回一条可归一化的源记录。"""

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
    """验证公开流程按资产查询，且结果不泄露源表定位字段。"""

    assets = InMemoryAssetRepository.g120_fixture()
    repository = RealDataRepository(
        FixtureExecutor(),
        source_timezone="UTC",
        create_time_filter_buffer_seconds=60,
        quality_settings=DataQualitySettings(
            nominal_interval_seconds=3,
            gap_warning_seconds=9,
            acceptable_completeness=0.95,
            insufficient_completeness=0.8,
        ),
    )
    service = TelemetryQueryService(
        AssetSourceResolver(assets),
        repository,
        policy=IamAuthorizationPolicy(
            IamPolicyConfig(engineer_asset_assignments={"engineer-1": frozenset({"asset-g120-1"})})
        ),
    )

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
