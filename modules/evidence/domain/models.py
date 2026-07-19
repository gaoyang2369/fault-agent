"""不可变证据快照以及必须绑定证据的声明模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetId, ClaimId, EvidenceId
from shared.time import TimeRange


class StrictModel(BaseModel):
    """拒绝未知字段且实例不可变的证据领域模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceType(StrEnum):
    """证据内容的来源与结构类别。"""

    TELEMETRY_SLICE = "TELEMETRY_SLICE"
    DATA_QUALITY = "DATA_QUALITY"
    REPORTED_FAULT_CODE = "REPORTED_FAULT_CODE"
    REPORTED_ALARM_CODE = "REPORTED_ALARM_CODE"
    RULE_HIT = "RULE_HIT"
    DOCUMENT_CHUNK = "DOCUMENT_CHUNK"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    USER_OBSERVATION = "USER_OBSERVATION"


class TelemetrySlicePayload(StrictModel):
    """描述一段遥测信号及其源记录范围的证据载荷。"""

    kind: Literal["TELEMETRY_SLICE"]
    signal_codes: tuple[str, ...] = Field(min_length=1)
    point_count: int = Field(ge=0)
    source_record_ids: tuple[str, ...]


class DataQualityPayload(StrictModel):
    """描述数据质量状态、完整率和告警代码的证据载荷。"""

    kind: Literal["DATA_QUALITY"]
    status: str
    completeness: float = Field(ge=0, le=1)
    warning_codes: tuple[str, ...] = ()


class ReportedCodePayload(StrictModel):
    """保留设备上报故障/告警原始码、规范码和源记录的证据载荷。"""

    kind: Literal["REPORTED_FAULT_CODE", "REPORTED_ALARM_CODE"]
    raw_code: str = Field(min_length=1)
    normalized_code: str | None = None
    source_record_ids: tuple[str, ...] = Field(min_length=1)


class RuleHitPayload(StrictModel):
    """描述确定性规则命中及其规则版本和观测摘要的证据载荷。"""

    kind: Literal["RULE_HIT"]
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    observed_value_summary: str = Field(min_length=1)


class DocumentChunkPayload(StrictModel):
    """描述知识文档版本、片段位置和摘录的证据载荷。"""

    kind: Literal["DOCUMENT_CHUNK"]
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    text_excerpt: str = Field(min_length=1)


class ModelInferencePayload(StrictModel):
    """描述模型版本、输出代码及输入证据集合的推理证据载荷。"""

    kind: Literal["MODEL_INFERENCE"]
    model_version: str = Field(min_length=1)
    output_code: str = Field(min_length=1)
    input_evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)


class UserObservationPayload(StrictModel):
    """描述由已知人员记录的现场观测事实证据。"""

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
    """保存可校验内容哈希、来源引用和结构化载荷的不可变证据快照。"""

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
        """校验证据时间带时区，且载荷判别类型与证据类型一致。"""

        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.payload.kind != self.evidence_type.value:
            raise ValueError("payload kind must match evidence_type")
        return self


class ClaimType(StrEnum):
    """声明的重要性类别。"""

    MATERIAL = "MATERIAL"
    INFORMATIONAL = "INFORMATIONAL"


class EvidenceStatus(StrEnum):
    """声明当前证据是否充分的状态。"""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class ClaimGenerator(StrEnum):
    """产生声明的主体或执行组件类别。"""

    SYSTEM = "SYSTEM"
    RULE_ENGINE = "RULE_ENGINE"
    MODEL = "MODEL"
    HUMAN = "HUMAN"


class Claim(StrictModel):
    """表达可追溯到支持/反驳证据的结构化声明。"""

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
        """校验创建时间，并强制实质性声明引用证据或明确证据不足。"""

        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if (
            self.claim_type is ClaimType.MATERIAL
            and not self.supporting_evidence_ids
            and self.evidence_status is not EvidenceStatus.INSUFFICIENT
        ):
            raise ValueError("material claim requires supporting evidence or INSUFFICIENT status")
        return self
