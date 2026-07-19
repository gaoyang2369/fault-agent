"""公开且已归一化的遥测领域值。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetId


class SignalQuality(StrEnum):
    """单个信号值的数据质量等级。"""

    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    BAD = "BAD"
    MISSING = "MISSING"


class SignalValue(BaseModel):
    """携带值、显式单位和质量状态的信号值对象。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | str | bool | None
    unit: str | None
    quality: SignalQuality


class Observation(BaseModel):
    """一条可追溯到源记录的信号观测，与诊断解释严格区分。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_record_id: str = Field(min_length=1)
    asset_id: AssetId
    observed_at: datetime
    signal_code: str = Field(min_length=1)
    value: float | str | bool | None
    unit: str | None
    quality: SignalQuality

    @model_validator(mode="after")
    def require_aware_time(self) -> "Observation":
        """确保观测时间包含明确时区。"""

        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return self


class TelemetryPoint(BaseModel):
    """汇总某一时刻资产的多个信号值及其源记录标识。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: datetime
    asset_id: AssetId
    values: dict[str, SignalValue]
    source_record_ids: tuple[str, ...]

    @model_validator(mode="after")
    def require_aware_time(self) -> "TelemetryPoint":
        """确保遥测点时间包含明确时区。"""

        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return self
