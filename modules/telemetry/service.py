"""Application service shared by HTTP controllers and Agent tools."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, timedelta
from itertools import pairwise
from math import ceil
from typing import Protocol

from modules.telemetry.models import (
    AggregationFunction,
    DataQualitySettings,
    DataQualityStatus,
    DataQualitySummary,
    DataQualityWarning,
    RequestContext,
    SignalValue,
    TelemetryPoint,
    TelemetryQuery,
    TelemetryQueryResult,
)
from modules.telemetry.repository import (
    NUMERIC_SIGNALS,
    NormalizedRow,
    RealDataRepository,
    RepositoryResult,
    numeric_value,
    raw_value,
)


class TelemetryPolicy(Protocol):
    def authorize(self, command: TelemetryQuery, context: RequestContext) -> TelemetryQuery: ...


class AllowAllTelemetryPolicy:
    """Temporary deterministic policy until Task 5 supplies IAM-backed policy."""

    def authorize(self, command: TelemetryQuery, context: RequestContext) -> TelemetryQuery:
        del context
        return command


class TelemetryQueryService:
    """Validate application policy, query the source, and shape bounded results."""

    def __init__(
        self,
        repository: RealDataRepository,
        *,
        quality_settings: DataQualitySettings,
        max_return_points: int = 10_000,
        policy: TelemetryPolicy | None = None,
    ) -> None:
        if max_return_points <= 0:
            raise ValueError("max_return_points must be greater than zero")
        self._repository = repository
        self._max_return_points = max_return_points
        self._quality_settings = quality_settings
        self._policy = policy or AllowAllTelemetryPolicy()

    def query(self, command: TelemetryQuery, context: RequestContext) -> TelemetryQueryResult:
        authorized = self._policy.authorize(command, context)
        maximum = min(authorized.max_points, self._max_return_points)
        repository_result = self._repository.query(
            device_name=authorized.device_name,
            inverter_name=authorized.inverter_name,
            start=authorized.start.astimezone(UTC),
            end=authorized.end.astimezone(UTC),
            signals=authorized.signals,
        )
        warnings = list(repository_result.warnings)
        if authorized.aggregation is None:
            points = [
                self._raw_point(row, authorized.signals, warnings)
                for row in sorted(repository_result.rows, key=lambda item: item.observed_at)
            ]
        else:
            points = self._aggregate(repository_result.rows, authorized, warnings)
        matched_rows = len(repository_result.rows)
        result_truncated = len(points) > maximum
        if result_truncated:
            points = points[:maximum]
            warnings.append(
                DataQualityWarning(
                    code="MAX_POINTS_EXCEEDED",
                    message="result was truncated to the configured maximum point count",
                )
            )
        return TelemetryQueryResult(
            points=tuple(points),
            warnings=tuple(warnings),
            scanned_rows=repository_result.scanned_rows,
            matched_rows=matched_rows,
            discarded_duplicate_count=repository_result.discarded_duplicate_count,
            truncated=repository_result.truncated or result_truncated,
            data_quality=self._summarize_quality(
                authorized, repository_result.rows, repository_result
            ),
        )

    def _summarize_quality(
        self,
        command: TelemetryQuery,
        rows: Sequence[NormalizedRow],
        repository_result: RepositoryResult,
    ) -> DataQualitySummary:
        gaps: list[float] = []
        groups: defaultdict[tuple[str | None, str | None], list[NormalizedRow]] = defaultdict(list)
        for row in rows:
            groups[
                (
                    _optional_text(row.raw.get("device_name")),
                    _optional_text(row.raw.get("inverter_name")),
                )
            ].append(row)
        for group_rows in groups.values():
            ordered = sorted(group_rows, key=lambda row: row.observed_at)
            gaps.extend(
                (current.observed_at - previous.observed_at).total_seconds()
                for previous, current in pairwise(ordered)
            )
        duration_seconds = (command.end - command.start).total_seconds()
        expected_per_series = ceil(
            duration_seconds / self._quality_settings.nominal_interval_seconds
        )
        expected_points = expected_per_series * max(len(groups), 1)
        observed_points = len(rows)
        completeness = min(observed_points / expected_points, 1.0) if expected_points else 0.0
        gap_count = sum(gap > self._quality_settings.gap_warning_seconds for gap in gaps)
        if (
            repository_result.truncated
            or completeness < self._quality_settings.insufficient_completeness
        ):
            status = DataQualityStatus.INSUFFICIENT
        elif (
            completeness < self._quality_settings.acceptable_completeness
            or repository_result.timestamp_parse_failure_count > 0
            or repository_result.discarded_duplicate_count > 0
            or gap_count > 0
        ):
            status = DataQualityStatus.DEGRADED
        else:
            status = DataQualityStatus.ACCEPTABLE
        allowed = ["POINT", "REPORTED_EVENT"]
        if status is not DataQualityStatus.INSUFFICIENT:
            allowed.append("TREND")
            if gap_count == 0:
                allowed.append("DURATION")
        return DataQualitySummary(
            status=status,
            expected_points=expected_points,
            observed_points=observed_points,
            valid_timestamp_points=(observed_points + repository_result.discarded_duplicate_count),
            completeness=completeness,
            timestamp_parse_failure_count=repository_result.timestamp_parse_failure_count,
            duplicate_count=repository_result.discarded_duplicate_count,
            gap_count=gap_count,
            maximum_gap_seconds=max(gaps) if gaps else None,
            allowed_analyses=tuple(allowed),
        )

    @staticmethod
    def _raw_point(
        row: NormalizedRow,
        signals: Sequence[str],
        warnings: list[DataQualityWarning],
    ) -> TelemetryPoint:
        values: dict[str, SignalValue] = {}
        record_id = str(row.raw.get("id"))
        for signal in signals:
            value = raw_value(row, signal)
            if signal in NUMERIC_SIGNALS:
                converted = numeric_value(value)
                quality = "GOOD" if converted is not None else "MISSING_OR_INVALID"
                if value is not None and converted is None:
                    warnings.append(
                        DataQualityWarning(
                            code="INVALID_SIGNAL_VALUE",
                            message=f"{signal} is not a finite numeric value",
                            source_record_ids=(record_id,),
                        )
                    )
                values[signal] = SignalValue(value=converted, quality=quality)
            else:
                quality = "GOOD" if value not in (None, "") else "MISSING"
                values[signal] = SignalValue(
                    value=None if value is None else str(value), quality=quality
                )
        return TelemetryPoint(
            observed_at=row.observed_at,
            device_name=_optional_text(row.raw.get("device_name")),
            inverter_name=_optional_text(row.raw.get("inverter_name")),
            source_record_ids=(record_id,),
            values=values,
        )

    def _aggregate(
        self,
        rows: Sequence[NormalizedRow],
        request: TelemetryQuery,
        warnings: list[DataQualityWarning],
    ) -> list[TelemetryPoint]:
        assert request.aggregation is not None
        non_numeric = sorted(set(request.signals) - NUMERIC_SIGNALS)
        if non_numeric:
            raise ValueError(f"aggregation only supports numeric signals: {', '.join(non_numeric)}")
        window = request.aggregation.window_seconds
        start = request.start.astimezone(UTC)
        buckets: defaultdict[tuple[str | None, str | None, int], list[NormalizedRow]] = defaultdict(
            list
        )
        for row in rows:
            bucket = int((row.observed_at - start).total_seconds() // window)
            key = (
                _optional_text(row.raw.get("device_name")),
                _optional_text(row.raw.get("inverter_name")),
                bucket,
            )
            buckets[key].append(row)
        points: list[TelemetryPoint] = []
        for (_, _, bucket_index), bucket_rows in sorted(
            buckets.items(), key=lambda item: (item[0][2], item[0][0] or "", item[0][1] or "")
        ):
            values: dict[str, SignalValue] = {}
            for signal in request.signals:
                samples = [
                    value
                    for row in bucket_rows
                    if (value := numeric_value(raw_value(row, signal))) is not None
                ]
                for function in request.aggregation.functions:
                    value_key = f"{signal}.{function.value}"
                    value = self._apply_aggregate(function, samples)
                    values[value_key] = SignalValue(
                        value=value,
                        quality="GOOD" if value is not None else "MISSING_OR_INVALID",
                    )
            points.append(
                TelemetryPoint(
                    observed_at=start + timedelta(seconds=bucket_index * window),
                    device_name=_optional_text(bucket_rows[0].raw.get("device_name")),
                    inverter_name=_optional_text(bucket_rows[0].raw.get("inverter_name")),
                    source_record_ids=tuple(str(row.raw.get("id")) for row in bucket_rows),
                    values=values,
                )
            )
        if rows and not points:
            warnings.append(
                DataQualityWarning(
                    code="AGGREGATION_EMPTY",
                    message="no valid values were available for aggregation",
                )
            )
        return points

    @staticmethod
    def _apply_aggregate(function: AggregationFunction, samples: Sequence[float]) -> float | None:
        if not samples:
            return None
        if function is AggregationFunction.MIN:
            return min(samples)
        if function is AggregationFunction.MAX:
            return max(samples)
        return sum(samples) / len(samples)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)
