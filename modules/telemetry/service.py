"""Application service shared by HTTP controllers and Agent tools."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, timedelta

from modules.telemetry.models import (
    AggregationFunction,
    DataQualityWarning,
    SignalValue,
    TelemetryPoint,
    TelemetryQuery,
    TelemetryQueryResult,
)
from modules.telemetry.repository import (
    NUMERIC_SIGNALS,
    NormalizedRow,
    RealDataRepository,
    numeric_value,
    raw_value,
)

type QueryPolicy = Callable[[TelemetryQuery], TelemetryQuery]


class TelemetryQueryService:
    """Validate application policy, query the source, and shape bounded results."""

    def __init__(
        self,
        repository: RealDataRepository,
        *,
        max_return_points: int = 10_000,
        policy: QueryPolicy | None = None,
    ) -> None:
        if max_return_points <= 0:
            raise ValueError("max_return_points must be greater than zero")
        self._repository = repository
        self._max_return_points = max_return_points
        self._policy = policy

    def query(self, request: TelemetryQuery) -> TelemetryQueryResult:
        authorized = self._policy(request) if self._policy is not None else request
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
            truncated=repository_result.truncated or result_truncated,
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
