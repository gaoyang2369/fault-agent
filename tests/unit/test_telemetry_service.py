"""Unit tests for application-layer telemetry behavior."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from modules.telemetry.models import (
    AggregationFunction,
    AggregationSpec,
    DataQualitySettings,
    RequestContext,
    TelemetryQuery,
)
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


def context() -> RequestContext:
    return RequestContext(
        request_id="request-1",
        trace_id="trace-1",
        user_id="authenticated-user",
        roles=("ENGINEER",),
    )


def quality_settings() -> DataQualitySettings:
    return DataQualitySettings(
        nominal_interval_seconds=3,
        gap_warning_seconds=9,
        acceptable_completeness=0.95,
        insufficient_completeness=0.80,
    )


def repository(rows: list[Row]) -> RealDataRepository:
    return RealDataRepository(
        FixtureExecutor(rows),
        source_timezone="UTC",
        create_time_filter_buffer_seconds=60,
    )


def test_query_contract_rejects_naive_time_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        query(start=datetime(2026, 7, 16))
    with pytest.raises(ValidationError):
        query(raw_sql="SELECT * FROM real_data")
    with pytest.raises(ValidationError):
        query(user_id="payload-user", roles=("ADMIN",))


def test_policy_is_application_layer_and_can_rewrite_request() -> None:
    requested: list[TelemetryQuery] = []

    class GuestPolicy:
        def authorize(
            self, command: TelemetryQuery, request_context: RequestContext
        ) -> TelemetryQuery:
            assert request_context.user_id == "authenticated-user"
            requested.append(command)
            return command.model_copy(
                update={
                    "aggregation": AggregationSpec(
                        window_seconds=60, functions=(AggregationFunction.AVG,)
                    )
                }
            )

    service = TelemetryQueryService(
        repository([]), quality_settings=quality_settings(), policy=GuestPolicy()
    )

    service.query(query(), context())

    assert requested


def test_service_limits_points_and_returns_invalid_value_warning() -> None:
    rows = [
        {"id": 1, "timestamp": "2026-07-16T00:00:00Z", "device_name": "D", "speed_actual": "bad"},
        {"id": 2, "timestamp": "2026-07-16T00:00:03Z", "device_name": "D", "speed_actual": 2},
    ]
    service = TelemetryQueryService(
        repository(rows), quality_settings=quality_settings(), max_return_points=1
    )

    result = service.query(query(max_points=2), context())

    assert len(result.points) == 1
    assert result.truncated is True
    assert {warning.code for warning in result.warnings} == {
        "INVALID_SIGNAL_VALUE",
        "MAX_POINTS_EXCEEDED",
    }


def test_aggregation_rejects_reported_event_fields() -> None:
    service = TelemetryQueryService(repository([]), quality_settings=quality_settings())
    request = query(
        signals=("fault_code",),
        aggregation=AggregationSpec(window_seconds=60, functions=(AggregationFunction.MAX,)),
    )
    with pytest.raises(ValueError, match="only supports numeric"):
        service.query(request, context())


def test_data_quality_summary_uses_configured_thresholds_and_gaps() -> None:
    rows = [
        {
            "id": 1,
            "timestamp": "2026-07-16T00:00:00Z",
            "device_name": "D",
            "speed_actual": 1,
        },
        {
            "id": 2,
            "timestamp": "2026-07-16T00:00:12Z",
            "device_name": "D",
            "speed_actual": 2,
        },
        {"id": 3, "timestamp": "bad", "device_name": "D", "speed_actual": 3},
    ]
    settings = DataQualitySettings(
        nominal_interval_seconds=6,
        gap_warning_seconds=10,
        acceptable_completeness=0.9,
        insufficient_completeness=0.4,
    )
    service = TelemetryQueryService(repository(rows), quality_settings=settings)

    result = service.query(query(end=datetime(2026, 7, 16, 0, 0, 24, tzinfo=UTC)), context())

    assert result.data_quality.status == "DEGRADED"
    assert result.data_quality.expected_points == 4
    assert result.data_quality.observed_points == 2
    assert result.data_quality.valid_timestamp_points == 2
    assert result.data_quality.completeness == 0.5
    assert result.data_quality.timestamp_parse_failure_count == 1
    assert result.data_quality.gap_count == 1
    assert result.data_quality.maximum_gap_seconds == 12
    assert result.data_quality.allowed_analyses == (
        "POINT",
        "REPORTED_EVENT",
        "TREND",
    )
