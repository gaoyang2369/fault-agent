"""为兼容 Task 3.1 保留的旧版源表导向契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """拒绝未知字段且实例不可变的旧版遥测模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AggregationFunction(StrEnum):
    """旧版查询支持的数值聚合函数。"""

    MIN = "min"
    MAX = "max"
    AVG = "avg"


class AggregationSpec(StrictModel):
    """旧版查询的聚合窗口与函数配置。"""

    window_seconds: int = Field(gt=0)
    functions: tuple[AggregationFunction, ...] = Field(min_length=1)


class TelemetryQuery(StrictModel):
    """已弃用的 Task 3.1 源表导向查询，新调用应使用 TelemetryQueryCommand。"""

    device_name: str | None = Field(default=None, min_length=1, max_length=255)
    inverter_name: str | None = Field(default=None, min_length=1, max_length=255)
    start: datetime
    end: datetime
    signals: tuple[str, ...] = Field(min_length=1)
    aggregation: AggregationSpec | None = None
    max_points: int = Field(default=10_000, gt=0)

    @model_validator(mode="after")
    def validate_query(self) -> TelemetryQuery:
        """校验源身份、时区、时间顺序及信号唯一性。"""

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
    """记录一次旧版查询的数据质量告警及关联源记录。"""

    code: str
    message: str
    source_record_ids: tuple[str, ...] = ()


class DataQualityStatus(StrEnum):
    """旧版查询的整体数据质量状态。"""

    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class DataQualitySummary(StrictModel):
    """旧版查询的数据完整性、时间质量、间隔与可用分析汇总。"""

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
    """通过显式配置提供采样周期、间隔和完整率判定参数。"""

    nominal_interval_seconds: float = Field(gt=0)
    gap_warning_seconds: float = Field(gt=0)
    acceptable_completeness: float = Field(ge=0.0, le=1.0)
    insufficient_completeness: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> DataQualitySettings:
        """确保“数据不足”完整率不高于“可接受”完整率。"""

        if self.insufficient_completeness > self.acceptable_completeness:
            raise ValueError("insufficient_completeness must not exceed acceptable_completeness")
        return self


class RequestContext(StrictModel):
    """已弃用的兼容上下文，新调用应使用 shared.context.RequestContext。"""

    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    roles: tuple[str, ...] = Field(min_length=1)


class SignalValue(StrictModel):
    """旧版查询返回的信号值、未知单位和质量文本。"""

    value: float | str | None
    unit: None = None
    quality: str


class TelemetryPoint(StrictModel):
    """旧版查询按源身份与观测时刻组织的遥测点。"""

    observed_at: datetime
    device_name: str | None
    inverter_name: str | None
    source_record_ids: tuple[str, ...]
    values: dict[str, SignalValue]


class TelemetryQueryResult(StrictModel):
    """旧版查询的点集、告警、扫描统计和数据质量结果。"""

    points: tuple[TelemetryPoint, ...]
    warnings: tuple[DataQualityWarning, ...]
    scanned_rows: int
    matched_rows: int
    discarded_duplicate_count: int
    truncated: bool
    data_quality: DataQualitySummary
