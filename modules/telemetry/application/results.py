"""Public telemetry query result."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from modules.telemetry.domain.models import TelemetryPoint
from modules.telemetry.domain.quality import DataQualitySummary
from shared.identifiers import AssetId
from shared.time import TimeRange


class SourceType(StrEnum):
    REAL_DATA = "REAL_DATA"


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: SourceType = SourceType.REAL_DATA
    scanned_rows: int = Field(ge=0)
    matched_rows: int = Field(ge=0)
    discarded_duplicate_count: int = Field(ge=0)
    truncated: bool


class TelemetryQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: AssetId
    time_range: TimeRange
    points: tuple[TelemetryPoint, ...]
    data_quality: DataQualitySummary
    warnings: tuple[str, ...]
    source_metadata: SourceMetadata
