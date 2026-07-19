"""诊断事实、解释、假设及人工确认模型。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.telemetry.domain.quality import DataQualitySummary
from shared.identifiers import AssetId, DiagnosisId, EvidenceId, UserId
from shared.time import TimeRange


class StrictModel(BaseModel):
    """拒绝未知字段且实例不可变的诊断领域模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EventType(StrEnum):
    """设备上报事件类别。"""

    FAULT = "FAULT"
    ALARM = "ALARM"
    STATUS_CHANGE = "STATUS_CHANGE"


class EventSource(StrEnum):
    """上报事件的数据来源类别。"""

    DEVICE_REPORTED = "DEVICE_REPORTED"


class ReportedEvent(StrictModel):
    """记录设备上报的故障、告警或状态变化事实，不代表根因确认。"""

    event_type: EventType
    event_code: str = Field(min_length=1)
    reported_at: datetime
    source: EventSource = EventSource.DEVICE_REPORTED
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_aware_reported_time(self) -> "ReportedEvent":
        """确保设备事件上报时间包含明确时区。"""

        if self.reported_at.tzinfo is None or self.reported_at.utcoffset() is None:
            raise ValueError("reported_at must be timezone-aware")
        return self


class AnomalySeverity(StrEnum):
    """确定性异常的严重程度枚举。"""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Anomaly(StrictModel):
    """描述由指定版本规则识别、且有证据支撑的运行异常。"""

    anomaly_id: str = Field(min_length=1)
    anomaly_type: str = Field(min_length=1)
    severity: AnomalySeverity
    time_range: TimeRange
    rule_id: str = Field(min_length=1)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)


class HypothesisTarget(StrEnum):
    """故障假设可能指向的组件范围。"""

    INVERTER = "INVERTER"
    MOTOR = "MOTOR"
    DRIVE_SYSTEM = "DRIVE_SYSTEM"
    UNKNOWN = "UNKNOWN"


class Hypothesis(StrictModel):
    """表达尚未确认的故障解释及其支持、反驳证据和待验证条件。"""

    hypothesis_id: str = Field(min_length=1)
    hypothesis_code: str = Field(min_length=1)
    target_component: HypothesisTarget
    score: float | None = Field(default=None, ge=0, le=1)
    supporting_evidence_ids: tuple[EvidenceId, ...] = ()
    contradicting_evidence_ids: tuple[EvidenceId, ...] = ()
    unverified_conditions: tuple[str, ...] = ()


class ConfirmationMethod(StrEnum):
    """工程师确认故障时采用的方法。"""

    INSPECTION = "INSPECTION"
    REPAIR_RESULT = "REPAIR_RESULT"
    MANUFACTURER_DIAGNOSTIC = "MANUFACTURER_DIAGNOSTIC"


class ConfirmedFault(StrictModel):
    """表示由已认证人员通过明确方法确认的故障事实。"""

    confirmed_fault_id: str = Field(min_length=1)
    fault_code: str = Field(min_length=1)
    confirmed_by: UserId
    confirmed_at: datetime
    confirmation_method: ConfirmationMethod
    source_hypothesis_id: str | None = None

    @model_validator(mode="after")
    def require_aware_confirmation(self) -> "ConfirmedFault":
        """确保人工确认时间包含明确时区。"""

        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return self


class DiagnosisStatus(StrEnum):
    """一次诊断运行的业务结果状态。"""

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
    """记录诊断运行使用的规则、知识和模型版本。"""

    rule_version: str = Field(min_length=1)
    knowledge_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)


class DiagnosisResult(StrictModel):
    """汇总数据质量、事件、异常、假设、证据及可选人工确认结果。"""

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
