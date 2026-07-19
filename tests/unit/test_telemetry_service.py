"""公开应用服务与正式 ``real_data`` 适配器的单元测试。"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.telemetry.application.commands import (
    AggregationFunction,
    AggregationSpec,
    TelemetryQueryCommand,
)
from modules.telemetry.application.ports import TelemetryAuthorizationPolicy
from modules.telemetry.application.service import TelemetryQueryService
from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)
from shared.context import RequestContext, RequestSource, Role


class FixtureExecutor:
    """为正式适配器返回预设源记录。"""

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        del sql, parameters
        return self.rows


def command(**overrides: object) -> TelemetryQueryCommand:
    """构造有效公开命令，并允许测试覆盖字段。"""

    values: dict[str, object] = {
        "asset_code": "G120-1",
        "time_range": {
            "start": datetime(2026, 7, 16, tzinfo=UTC),
            "end": datetime(2026, 7, 16, 1, tzinfo=UTC),
        },
        "signal_codes": ("speed_actual",),
    }
    values.update(overrides)
    return TelemetryQueryCommand.model_validate(values)


def context() -> RequestContext:
    """构造由可信边界提供的工程师上下文。"""

    return RequestContext(
        request_id="request-1",
        trace_id="trace-1",
        user_id="authenticated-user",
        roles=frozenset({Role.ENGINEER}),
        request_source=RequestSource.HTTP,
    )


def quality_settings(**overrides: float) -> DataQualitySettings:
    values = {
        "nominal_interval_seconds": 3.0,
        "gap_warning_seconds": 9.0,
        "acceptable_completeness": 0.95,
        "insufficient_completeness": 0.8,
    }
    values.update(overrides)
    return DataQualitySettings.model_validate(values)


def service(
    rows: list[Row],
    *,
    settings: DataQualitySettings | None = None,
    max_return_points: int = 10_000,
    policy: TelemetryAuthorizationPolicy | None = None,
) -> TelemetryQueryService:
    repository = RealDataRepository(
        FixtureExecutor(rows),
        source_timezone="UTC",
        create_time_filter_buffer_seconds=60,
        quality_settings=settings or quality_settings(),
        max_return_points=max_return_points,
    )
    return TelemetryQueryService(
        AssetSourceResolver(InMemoryAssetRepository.g120_fixture()),
        repository,
        policy=policy,
    )


def test_query_contract_rejects_naive_time_and_unknown_fields() -> None:
    """验证公开命令拒绝无时区时间、源定位、身份和原始 SQL。"""

    with pytest.raises(ValidationError):
        command(time_range={"start": datetime(2026, 7, 16), "end": datetime(2026, 7, 17)})
    for forbidden in (
        {"raw_sql": "SELECT * FROM real_data"},
        {"user_id": "payload-user"},
        {"device_name": "D"},
    ):
        with pytest.raises(ValidationError):
            command(**forbidden)


def test_policy_is_application_layer_and_can_rewrite_request() -> None:
    """验证授权位于应用层，且策略可确定性收紧命令。"""

    requested: list[TelemetryQueryCommand] = []

    class GuestPolicy:
        def authorize(
            self, command: TelemetryQueryCommand, asset: object, request_context: RequestContext
        ) -> TelemetryQueryCommand:
            del asset
            assert request_context.user_id == "authenticated-user"
            requested.append(command)
            return command.model_copy(
                update={
                    "aggregation": AggregationSpec(
                        window_seconds=60, functions=(AggregationFunction.AVG,)
                    )
                }
            )

    asyncio.run(service([], policy=GuestPolicy()).query(command(), context()))
    assert requested


def test_service_limits_points_and_returns_invalid_value_warning() -> None:
    rows: list[Row] = [
        {"id": 1, "timestamp": "2026-07-16T00:00:00Z", "speed_actual": "bad"},
        {"id": 2, "timestamp": "2026-07-16T00:00:03Z", "speed_actual": 2},
    ]
    result = asyncio.run(service(rows, max_return_points=1).query(command(max_points=2), context()))

    assert len(result.points) == 1
    assert result.source_metadata.truncated is True
    assert set(result.warnings) == {"INVALID_SIGNAL_VALUE", "MAX_POINTS_EXCEEDED"}


def test_aggregation_rejects_reported_event_fields() -> None:
    request = command(
        signal_codes=("fault_code",),
        aggregation=AggregationSpec(window_seconds=60, functions=(AggregationFunction.MAX,)),
    )
    with pytest.raises(ValueError, match="only supports numeric"):
        asyncio.run(service([]).query(request, context()))


def test_data_quality_summary_uses_configured_thresholds_and_gaps() -> None:
    rows: list[Row] = [
        {"id": 1, "timestamp": "2026-07-16T00:00:00Z", "speed_actual": 1},
        {"id": 2, "timestamp": "2026-07-16T00:00:12Z", "speed_actual": 2},
        {"id": 3, "timestamp": "bad", "speed_actual": 3},
    ]
    settings = quality_settings(
        nominal_interval_seconds=6,
        gap_warning_seconds=10,
        acceptable_completeness=0.9,
        insufficient_completeness=0.4,
    )
    request = command(
        time_range={
            "start": datetime(2026, 7, 16, tzinfo=UTC),
            "end": datetime(2026, 7, 16, 0, 0, 24, tzinfo=UTC),
        }
    )
    result = asyncio.run(service(rows, settings=settings).query(request, context()))

    assert result.data_quality.status == "DEGRADED"
    assert result.data_quality.expected_points == 4
    assert result.data_quality.observed_points == 2
    assert result.data_quality.valid_timestamp_points == 2
    assert result.data_quality.completeness == 0.5
    assert result.data_quality.timestamp_parse_failure_count == 1
    assert result.data_quality.gap_count == 1
    assert result.data_quality.maximum_gap_seconds == 12
    assert result.data_quality.allowed_analyses == (
        "POINT_SUMMARY",
        "REPORTED_EVENT_DETECTION",
        "TREND_ANALYSIS",
    )
