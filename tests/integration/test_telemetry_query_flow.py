"""Integration test across query contract, repository, and application service."""

from collections.abc import Sequence
from datetime import UTC, datetime

from modules.telemetry.models import AggregationFunction, AggregationSpec, TelemetryQuery
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
    service = TelemetryQueryService(RealDataRepository(source, source_timezone="Asia/Shanghai"))
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

    result = service.query(request)

    assert result.matched_rows == 3
    assert [point.observed_at for point in result.points] == [
        datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
        datetime(2026, 7, 16, 0, 1, tzinfo=UTC),
    ]
    assert result.points[0].values["speed_actual.min"].value == 10
    assert result.points[0].values["speed_actual.max"].value == 20
    assert result.points[0].values["speed_actual.avg"].value == 15
    assert all(value.unit is None for point in result.points for value in point.values.values())
