"""诊断模块的领域模型包。"""

from modules.diagnosis.domain.models import (
    Anomaly,
    ConfirmedFault,
    DiagnosisRequest,
    DiagnosisResult,
    Hypothesis,
    Recommendation,
    ReportedEvent,
)

__all__ = [
    "Anomaly",
    "ConfirmedFault",
    "DiagnosisRequest",
    "DiagnosisResult",
    "Hypothesis",
    "Recommendation",
    "ReportedEvent",
]
