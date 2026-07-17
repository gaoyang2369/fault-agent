"""Public telemetry query command; source identities and auth are forbidden."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetCode, AssetId
from shared.time import TimeRange


class AggregationFunction(StrEnum):
    MIN = "MIN"
    MAX = "MAX"
    AVG = "AVG"


class AggregationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_seconds: int = Field(gt=0)
    functions: tuple[AggregationFunction, ...] = Field(min_length=1)


class TelemetryQueryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: AssetId | None = None
    asset_code: AssetCode | None = None
    time_range: TimeRange
    signal_codes: tuple[str, ...] = Field(min_length=1)
    aggregation: AggregationSpec | None = None
    max_points: int = Field(default=10_000, gt=0)

    @model_validator(mode="after")
    def validate_identity_and_signals(self) -> "TelemetryQueryCommand":
        if (self.asset_id is None) == (self.asset_code is None):
            raise ValueError("exactly one of asset_id or asset_code is required")
        if len(self.signal_codes) != len(set(self.signal_codes)):
            raise ValueError("signal_codes must not contain duplicates")
        return self
