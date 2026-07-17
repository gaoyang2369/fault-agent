"""Immutable evidence snapshots and evidence-bound claims."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetId, ClaimId, EvidenceId
from shared.time import TimeRange


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceType(StrEnum):
    TELEMETRY_SLICE = "TELEMETRY_SLICE"
    DATA_QUALITY = "DATA_QUALITY"
    REPORTED_FAULT_CODE = "REPORTED_FAULT_CODE"
    REPORTED_ALARM_CODE = "REPORTED_ALARM_CODE"
    RULE_HIT = "RULE_HIT"
    DOCUMENT_CHUNK = "DOCUMENT_CHUNK"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    USER_OBSERVATION = "USER_OBSERVATION"


class TelemetrySlicePayload(StrictModel):
    kind: Literal["TELEMETRY_SLICE"]
    signal_codes: tuple[str, ...] = Field(min_length=1)
    point_count: int = Field(ge=0)
    source_record_ids: tuple[str, ...]


class DataQualityPayload(StrictModel):
    kind: Literal["DATA_QUALITY"]
    status: str
    completeness: float = Field(ge=0, le=1)
    warning_codes: tuple[str, ...] = ()


class ReportedCodePayload(StrictModel):
    kind: Literal["REPORTED_FAULT_CODE", "REPORTED_ALARM_CODE"]
    raw_code: str = Field(min_length=1)
    normalized_code: str | None = None
    source_record_ids: tuple[str, ...] = Field(min_length=1)


class RuleHitPayload(StrictModel):
    kind: Literal["RULE_HIT"]
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    observed_value_summary: str = Field(min_length=1)


class DocumentChunkPayload(StrictModel):
    kind: Literal["DOCUMENT_CHUNK"]
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    text_excerpt: str = Field(min_length=1)


class ModelInferencePayload(StrictModel):
    kind: Literal["MODEL_INFERENCE"]
    model_version: str = Field(min_length=1)
    output_code: str = Field(min_length=1)
    input_evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)


class UserObservationPayload(StrictModel):
    kind: Literal["USER_OBSERVATION"]
    observation_code: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    recorded_by: str = Field(min_length=1)


EvidencePayload = Annotated[
    TelemetrySlicePayload
    | DataQualityPayload
    | ReportedCodePayload
    | RuleHitPayload
    | DocumentChunkPayload
    | ModelInferencePayload
    | UserObservationPayload,
    Field(discriminator="kind"),
]


class Evidence(StrictModel):
    evidence_id: EvidenceId
    evidence_type: EvidenceType
    asset_id: AssetId
    time_range: TimeRange | None = None
    source: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    payload: EvidencePayload

    @model_validator(mode="after")
    def validate_snapshot(self) -> "Evidence":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.payload.kind != self.evidence_type.value:
            raise ValueError("payload kind must match evidence_type")
        return self


class ClaimType(StrEnum):
    MATERIAL = "MATERIAL"
    INFORMATIONAL = "INFORMATIONAL"


class EvidenceStatus(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class ClaimGenerator(StrEnum):
    SYSTEM = "SYSTEM"
    RULE_ENGINE = "RULE_ENGINE"
    MODEL = "MODEL"
    HUMAN = "HUMAN"


class Claim(StrictModel):
    claim_id: ClaimId
    claim_type: ClaimType
    statement_code: str = Field(min_length=1)
    supporting_evidence_ids: tuple[EvidenceId, ...] = ()
    contradicting_evidence_ids: tuple[EvidenceId, ...] = ()
    evidence_status: EvidenceStatus = EvidenceStatus.SUFFICIENT
    generated_by: ClaimGenerator
    created_at: datetime

    @model_validator(mode="after")
    def validate_evidence(self) -> "Claim":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if (
            self.claim_type is ClaimType.MATERIAL
            and not self.supporting_evidence_ids
            and self.evidence_status is not EvidenceStatus.INSUFFICIENT
        ):
            raise ValueError("material claim requires supporting evidence or INSUFFICIENT status")
        return self
