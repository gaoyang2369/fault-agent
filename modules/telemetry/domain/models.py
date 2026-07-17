"""Public normalized telemetry values."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetId


class SignalQuality(StrEnum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    BAD = "BAD"
    MISSING = "MISSING"


class SignalValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | str | bool | None
    unit: str | None
    quality: SignalQuality


class Observation(BaseModel):
    """One source-backed signal observation, distinct from diagnostic interpretation."""

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
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return self


class TelemetryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: datetime
    asset_id: AssetId
    values: dict[str, SignalValue]
    source_record_ids: tuple[str, ...]

    @model_validator(mode="after")
    def require_aware_time(self) -> "TelemetryPoint":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return self
