"""Diagnostic facts, interpretations, hypotheses, and human confirmations."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.telemetry.domain.quality import DataQualitySummary
from shared.identifiers import AssetId, DiagnosisId, EvidenceId, UserId
from shared.time import TimeRange


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EventType(StrEnum):
    FAULT = "FAULT"
    ALARM = "ALARM"
    STATUS_CHANGE = "STATUS_CHANGE"


class EventSource(StrEnum):
    DEVICE_REPORTED = "DEVICE_REPORTED"


class ReportedEvent(StrictModel):
    event_type: EventType
    event_code: str = Field(min_length=1)
    reported_at: datetime
    source: EventSource = EventSource.DEVICE_REPORTED
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_aware_reported_time(self) -> "ReportedEvent":
        if self.reported_at.tzinfo is None or self.reported_at.utcoffset() is None:
            raise ValueError("reported_at must be timezone-aware")
        return self


class AnomalySeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Anomaly(StrictModel):
    anomaly_id: str = Field(min_length=1)
    anomaly_type: str = Field(min_length=1)
    severity: AnomalySeverity
    time_range: TimeRange
    rule_id: str = Field(min_length=1)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)


class HypothesisTarget(StrEnum):
    INVERTER = "INVERTER"
    MOTOR = "MOTOR"
    DRIVE_SYSTEM = "DRIVE_SYSTEM"
    UNKNOWN = "UNKNOWN"


class Hypothesis(StrictModel):
    hypothesis_id: str = Field(min_length=1)
    hypothesis_code: str = Field(min_length=1)
    target_component: HypothesisTarget
    score: float | None = Field(default=None, ge=0, le=1)
    supporting_evidence_ids: tuple[EvidenceId, ...] = ()
    contradicting_evidence_ids: tuple[EvidenceId, ...] = ()
    unverified_conditions: tuple[str, ...] = ()


class ConfirmationMethod(StrEnum):
    INSPECTION = "INSPECTION"
    REPAIR_RESULT = "REPAIR_RESULT"
    MANUFACTURER_DIAGNOSTIC = "MANUFACTURER_DIAGNOSTIC"


class ConfirmedFault(StrictModel):
    confirmed_fault_id: str = Field(min_length=1)
    fault_code: str = Field(min_length=1)
    confirmed_by: UserId
    confirmed_at: datetime
    confirmation_method: ConfirmationMethod
    source_hypothesis_id: str | None = None

    @model_validator(mode="after")
    def require_aware_confirmation(self) -> "ConfirmedFault":
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return self


class DiagnosisStatus(StrEnum):
    NO_DATA = "NO_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_DEVICE_EVENT_OR_ENABLED_ANOMALY = "NO_DEVICE_EVENT_OR_ENABLED_ANOMALY"
    DEVICE_ALARM_REPORTED = "DEVICE_ALARM_REPORTED"
    DEVICE_FAULT_REPORTED = "DEVICE_FAULT_REPORTED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    HYPOTHESES_AVAILABLE = "HYPOTHESES_AVAILABLE"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"


class DiagnosisVersions(StrictModel):
    rule_version: str = Field(min_length=1)
    knowledge_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)


class DiagnosisResult(StrictModel):
    diagnosis_id: DiagnosisId
    asset_id: AssetId
    time_range: TimeRange
    status: DiagnosisStatus
    data_quality: DataQualitySummary
    reported_events: tuple[ReportedEvent, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    confirmed_fault: ConfirmedFault | None = None
    evidence_ids: tuple[EvidenceId, ...] = ()
    versions: DiagnosisVersions
