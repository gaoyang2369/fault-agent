"""Integration test across query contract, repository, and application service."""

from collections.abc import Sequence
from datetime import UTC, datetime

from modules.telemetry.models import (
    AggregationFunction,
    AggregationSpec,
    DataQualitySettings,
    RequestContext,
    TelemetryQuery,
)
from modules.telemetry.repository import RealDataRepository, Row
from modules.telemetry.service import TelemetryQueryService


class SourceFixture:
    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        assert sql.startswith("SELECT ")
        assert sql.endswith("LIMIT %s")
        return self.rows


def test_normalized_aggregated_query_flow() -> None:
    source = SourceFixture(
        [
            {
                "id": 10,
                "timestamp": "",
                "date": "2026-07-16",
                "time": "08:00:01",
                "device_name": "D",
                "inverter_name": "I",
                "speed_actual": "10",
            },
            {
                "id": 11,
                "timestamp": "2026-07-16 08:00:30",
                "date": None,
                "time": None,
                "device_name": "D",
                "inverter_name": "I",
                "speed_actual": 20,
                "create_time": datetime(2026, 7, 16, 8, 0, 31),
            },
            {
                "id": 13,
                "timestamp": "2026-07-16 08:00:30",
                "date": None,
                "time": None,
                "device_name": "D",
                "inverter_name": "I",
                "speed_actual": 40,
                "create_time": datetime(2026, 7, 16, 8, 0, 32),
            },
            {
                "id": 12,
                "timestamp": "2026-07-16 08:01:00",
                "date": None,
                "time": None,
                "device_name": "D",
                "inverter_name": "I",
                "speed_actual": 30,
            },
        ]
    )
    service = TelemetryQueryService(
        RealDataRepository(
            source,
            source_timezone="Asia/Shanghai",
            create_time_filter_buffer_seconds=3600,
        ),
        quality_settings=DataQualitySettings(
            nominal_interval_seconds=30,
            gap_warning_seconds=60,
            acceptable_completeness=0.75,
            insufficient_completeness=0.50,
        ),
    )
    request = TelemetryQuery(
        device_name="D",
        inverter_name="I",
        start=datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
        end=datetime(2026, 7, 16, 0, 2, tzinfo=UTC),
        signals=("speed_actual",),
        aggregation=AggregationSpec(
            window_seconds=60,
            functions=(
                AggregationFunction.MIN,
                AggregationFunction.MAX,
                AggregationFunction.AVG,
            ),
        ),
    )

    result = service.query(
        request,
        RequestContext(
            request_id="request-integration",
            trace_id="trace-integration",
            user_id="engineer-1",
            roles=("ENGINEER",),
        ),
    )

    assert result.matched_rows == 3
    assert result.discarded_duplicate_count == 1
    assert [point.observed_at for point in result.points] == [
        datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
        datetime(2026, 7, 16, 0, 1, tzinfo=UTC),
    ]
    assert result.points[0].values["speed_actual.min"].value == 10
    assert result.points[0].values["speed_actual.max"].value == 40
    assert result.points[0].values["speed_actual.avg"].value == 25
    assert result.points[0].source_record_ids == ("10", "13")
    assert all(value.unit is None for point in result.points for value in point.values.values())
