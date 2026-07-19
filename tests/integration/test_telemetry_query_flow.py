"""跨公开命令、资产解析、正式仓储和应用服务的集成测试。"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.telemetry.application.commands import (
    AggregationFunction,
    AggregationSpec,
    TelemetryQueryCommand,
)
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)
from shared.context import RequestContext, RequestSource, Role


class SourceFixture:
    """保存源记录并验证固定 SQL 查询形状。"""

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        assert sql.startswith("SELECT ")
        assert sql.endswith("LIMIT %s")
        assert parameters[:2] == ("G120电机1", "G120电机1")
        return self.rows


def test_normalized_aggregated_public_query_flow() -> None:
    """验证从公开资产命令到归一化聚合结果的完整流程。"""

    source = SourceFixture(
        [
            {
                "id": 10,
                "timestamp": "",
                "date": "2026-07-16",
                "time": "08:00:01",
                "device_name": "G120电机1",
                "inverter_name": "G120电机1",
                "speed_actual": "10",
            },
            {
                "id": 11,
                "timestamp": "2026-07-16 08:00:30",
                "device_name": "G120电机1",
                "inverter_name": "G120电机1",
                "speed_actual": 20,
                "create_time": datetime(2026, 7, 16, 8, 0, 31),
            },
            {
                "id": 13,
                "timestamp": "2026-07-16 08:00:30",
                "device_name": "G120电机1",
                "inverter_name": "G120电机1",
                "speed_actual": 40,
                "create_time": datetime(2026, 7, 16, 8, 0, 32),
            },
            {
                "id": 12,
                "timestamp": "2026-07-16 08:01:00",
                "device_name": "G120电机1",
                "inverter_name": "G120电机1",
                "speed_actual": 30,
            },
        ]
    )
    repository = RealDataRepository(
        source,
        source_timezone="Asia/Shanghai",
        create_time_filter_buffer_seconds=3600,
        quality_settings=DataQualitySettings(
            nominal_interval_seconds=30,
            gap_warning_seconds=60,
            acceptable_completeness=0.75,
            insufficient_completeness=0.5,
        ),
    )
    service = TelemetryQueryService(
        AssetSourceResolver(InMemoryAssetRepository.g120_fixture()), repository
    )
    request = TelemetryQueryCommand.model_validate(
        {
            "asset_code": "G120-1",
            "time_range": {
                "start": datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
                "end": datetime(2026, 7, 16, 0, 2, tzinfo=UTC),
            },
            "signal_codes": ("speed_actual",),
            "aggregation": AggregationSpec(
                window_seconds=60,
                functions=(
                    AggregationFunction.MIN,
                    AggregationFunction.MAX,
                    AggregationFunction.AVG,
                ),
            ),
        }
    )
    context = RequestContext(
        request_id="request-integration",
        trace_id="trace-integration",
        user_id="engineer-1",
        roles=frozenset({Role.ENGINEER}),
        request_source=RequestSource.INTERNAL,
    )

    result = asyncio.run(service.query(request, context))

    assert result.asset_id == "asset-g120-1"
    assert result.source_metadata.matched_rows == 3
    assert result.source_metadata.discarded_duplicate_count == 1
    assert [point.observed_at for point in result.points] == [
        datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
        datetime(2026, 7, 16, 0, 1, tzinfo=UTC),
    ]
    assert result.points[0].values["speed_actual.min"].value == 10
    assert result.points[0].values["speed_actual.max"].value == 40
    assert result.points[0].values["speed_actual.avg"].value == 25
    assert result.points[0].source_record_ids == ("10", "13")
    assert "device_name" not in result.model_dump_json()
