"""Unit tests for application-layer telemetry behavior."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from modules.telemetry.models import AggregationFunction, AggregationSpec, TelemetryQuery
from modules.telemetry.repository import RealDataRepository, Row
from modules.telemetry.service import TelemetryQueryService


class FixtureExecutor:
    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        return self.rows


def query(**overrides: object) -> TelemetryQuery:
    values: dict[str, object] = {
        "device_name": "D",
        "start": datetime(2026, 7, 16, tzinfo=UTC),
        "end": datetime(2026, 7, 16, 1, tzinfo=UTC),
        "signals": ("speed_actual",),
    }
    values.update(overrides)
    return TelemetryQuery.model_validate(values)


def test_query_contract_rejects_naive_time_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        query(start=datetime(2026, 7, 16))
    with pytest.raises(ValidationError):
        query(raw_sql="SELECT * FROM real_data")


def test_policy_is_application_layer_and_can_rewrite_request() -> None:
    requested: list[TelemetryQuery] = []

    def guest_policy(request: TelemetryQuery) -> TelemetryQuery:
        requested.append(request)
        return request.model_copy(
            update={
                "aggregation": AggregationSpec(
                    window_seconds=60, functions=(AggregationFunction.AVG,)
                )
            }
        )

    repository = RealDataRepository(FixtureExecutor([]), source_timezone="UTC")
    service = TelemetryQueryService(repository, policy=guest_policy)

    service.query(query())

    assert requested


def test_service_limits_points_and_returns_invalid_value_warning() -> None:
    rows = [
        {"id": 1, "timestamp": "2026-07-16T00:00:00Z", "device_name": "D", "speed_actual": "bad"},
        {"id": 2, "timestamp": "2026-07-16T00:00:03Z", "device_name": "D", "speed_actual": 2},
    ]
    service = TelemetryQueryService(
        RealDataRepository(FixtureExecutor(rows), source_timezone="UTC"), max_return_points=1
    )

    result = service.query(query(max_points=2))

    assert len(result.points) == 1
    assert result.truncated is True
    assert {warning.code for warning in result.warnings} == {
        "INVALID_SIGNAL_VALUE",
        "MAX_POINTS_EXCEEDED",
    }


def test_aggregation_rejects_reported_event_fields() -> None:
    service = TelemetryQueryService(RealDataRepository(FixtureExecutor([]), source_timezone="UTC"))
    request = query(
        signals=("fault_code",),
        aggregation=AggregationSpec(window_seconds=60, functions=(AggregationFunction.MAX,)),
    )
    with pytest.raises(ValueError, match="only supports numeric"):
        service.query(request)
