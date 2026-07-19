"""生成需要提交到仓库的公开 JSON Schema 契约。"""

import json
from pathlib import Path

from pydantic import BaseModel

from modules.asset.domain.models import DriveSystem, SignalDefinition
from modules.diagnosis.domain.models import (
    Anomaly,
    ConfirmedFault,
    DiagnosisResult,
    Hypothesis,
    ReportedEvent,
)
from modules.evidence.domain.models import Claim, Evidence
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from modules.telemetry.domain.quality import DataQualitySummary
from shared.context import RequestContext
from shared.errors import ErrorResponse

SCHEMAS: dict[str, type[BaseModel]] = {
    "request-context.schema.json": RequestContext,
    "asset.schema.json": DriveSystem,
    "signal-definition.schema.json": SignalDefinition,
    "telemetry-query-command.schema.json": TelemetryQueryCommand,
    "telemetry-query-result.schema.json": TelemetryQueryResult,
    "data-quality-summary.schema.json": DataQualitySummary,
    "evidence.schema.json": Evidence,
    "claim.schema.json": Claim,
    "reported-event.schema.json": ReportedEvent,
    "anomaly.schema.json": Anomaly,
    "hypothesis.schema.json": Hypothesis,
    "confirmed-fault.schema.json": ConfirmedFault,
    "diagnosis-result.schema.json": DiagnosisResult,
    "error-response.schema.json": ErrorResponse,
}


def main() -> None:
    """从当前 Pydantic 公开模型重新生成全部 JSON Schema 文件。"""

    output = Path(__file__).with_name("jsonschema")
    output.mkdir(exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (output / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
