"""Data quality gates used by downstream diagnosis."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataQualityStatus(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class AllowedAnalysis(StrEnum):
    POINT_SUMMARY = "POINT_SUMMARY"
    REPORTED_EVENT_DETECTION = "REPORTED_EVENT_DETECTION"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    DURATION_RULES = "DURATION_RULES"


class DataQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: DataQualityStatus
    expected_points: int = Field(ge=0)
    observed_points: int = Field(ge=0)
    valid_timestamp_points: int = Field(ge=0)
    completeness: float = Field(ge=0, le=1)
    timestamp_parse_failure_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    maximum_gap_seconds: float | None = Field(default=None, ge=0)
    allowed_analyses: tuple[AllowedAnalysis, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def gate_sequence_analyses(self) -> "DataQualitySummary":
        allowed = set(self.allowed_analyses)
        if self.status is DataQualityStatus.INSUFFICIENT and allowed.intersection(
            {AllowedAnalysis.TREND_ANALYSIS, AllowedAnalysis.DURATION_RULES}
        ):
            raise ValueError("insufficient data cannot enable trend or duration analyses")
        if self.gap_count and AllowedAnalysis.DURATION_RULES in allowed:
            raise ValueError("duration rules cannot cross known gaps")
        return self
