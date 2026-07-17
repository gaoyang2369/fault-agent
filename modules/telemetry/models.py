"""Deprecated Task 3.1 source-oriented contracts kept for compatibility."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AggregationFunction(StrEnum):
    MIN = "min"
    MAX = "max"
    AVG = "avg"


class AggregationSpec(StrictModel):
    window_seconds: int = Field(gt=0)
    functions: tuple[AggregationFunction, ...] = Field(min_length=1)


class TelemetryQuery(StrictModel):
    """Deprecated Task 3.1 source-oriented query; use TelemetryQueryCommand."""

    device_name: str | None = Field(default=None, min_length=1, max_length=255)
    inverter_name: str | None = Field(default=None, min_length=1, max_length=255)
    start: datetime
    end: datetime
    signals: tuple[str, ...] = Field(min_length=1)
    aggregation: AggregationSpec | None = None
    max_points: int = Field(default=10_000, gt=0)

    @model_validator(mode="after")
    def validate_query(self) -> TelemetryQuery:
        if self.device_name is None and self.inverter_name is None:
            raise ValueError("device_name or inverter_name is required")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("start must be before end")
        if len(set(self.signals)) != len(self.signals):
            raise ValueError("signals must not contain duplicates")
        return self


class DataQualityWarning(StrictModel):
    code: str
    message: str
    source_record_ids: tuple[str, ...] = ()


class DataQualityStatus(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class DataQualitySummary(StrictModel):
    status: DataQualityStatus
    expected_points: int = Field(ge=0)
    observed_points: int = Field(ge=0)
    valid_timestamp_points: int = Field(ge=0)
    completeness: float = Field(ge=0.0, le=1.0)
    timestamp_parse_failure_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    maximum_gap_seconds: float | None = Field(default=None, ge=0.0)
    allowed_analyses: tuple[str, ...]


class DataQualitySettings(StrictModel):
    nominal_interval_seconds: float = Field(gt=0)
    gap_warning_seconds: float = Field(gt=0)
    acceptable_completeness: float = Field(ge=0.0, le=1.0)
    insufficient_completeness: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> DataQualitySettings:
        if self.insufficient_completeness > self.acceptable_completeness:
            raise ValueError("insufficient_completeness must not exceed acceptable_completeness")
        return self


class RequestContext(StrictModel):
    """Deprecated compatibility context; use shared.context.RequestContext."""

    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    roles: tuple[str, ...] = Field(min_length=1)


class SignalValue(StrictModel):
    value: float | str | None
    unit: None = None
    quality: str


class TelemetryPoint(StrictModel):
    observed_at: datetime
    device_name: str | None
    inverter_name: str | None
    source_record_ids: tuple[str, ...]
    values: dict[str, SignalValue]


class TelemetryQueryResult(StrictModel):
    points: tuple[TelemetryPoint, ...]
    warnings: tuple[DataQualityWarning, ...]
    scanned_rows: int
    matched_rows: int
    discarded_duplicate_count: int
    truncated: bool
    data_quality: DataQualitySummary
