"""供下游诊断使用的数据质量门控模型。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataQualityStatus(StrEnum):
    """查询数据整体质量状态。"""

    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class AllowedAnalysis(StrEnum):
    """在当前数据质量下允许执行的分析类别。"""

    POINT_SUMMARY = "POINT_SUMMARY"
    REPORTED_EVENT_DETECTION = "REPORTED_EVENT_DETECTION"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    DURATION_RULES = "DURATION_RULES"


class DataQualitySummary(BaseModel):
    """汇总完整率、时间解析、重复与间隔质量，并声明允许的分析。"""

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
        """在数据不足或存在已知间隔时禁用相应时序分析。"""

        allowed = set(self.allowed_analyses)
        if self.status is DataQualityStatus.INSUFFICIENT and allowed.intersection(
            {AllowedAnalysis.TREND_ANALYSIS, AllowedAnalysis.DURATION_RULES}
        ):
            raise ValueError("insufficient data cannot enable trend or duration analyses")
        if self.gap_count and AllowedAnalysis.DURATION_RULES in allowed:
            raise ValueError("duration rules cannot cross known gaps")
        return self
