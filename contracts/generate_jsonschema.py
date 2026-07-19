"""生成需要提交到仓库的公开 JSON Schema 契约。"""

import json
from pathlib import Path

from pydantic import BaseModel

from contracts.version import PUBLIC_CONTRACT_ID_PREFIX, PUBLIC_CONTRACT_VERSION
from modules.asset.domain.models import Component, DriveSystem, SignalDefinition
from modules.diagnosis.domain.models import (
    Anomaly,
    ConfirmedFault,
    DiagnosisRequest,
    DiagnosisResult,
    Hypothesis,
    Recommendation,
    ReportedEvent,
)
from modules.evidence.domain.models import Claim, Evidence
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from modules.telemetry.domain.models import Observation
from modules.telemetry.domain.quality import DataQualitySummary
from shared.context import RequestContext
from shared.errors import ErrorResponse
from shared.time import TimeRange

SCHEMAS: dict[str, type[BaseModel]] = {
    "request-context.schema.json": RequestContext,
    "drive-system.schema.json": DriveSystem,
    # Compatibility alias retained for the already-published Task 4 schema name.
    "asset.schema.json": DriveSystem,
    "component.schema.json": Component,
    "signal-definition.schema.json": SignalDefinition,
    "time-range.schema.json": TimeRange,
    "observation.schema.json": Observation,
    "telemetry-query-command.schema.json": TelemetryQueryCommand,
    "telemetry-query-result.schema.json": TelemetryQueryResult,
    "data-quality-summary.schema.json": DataQualitySummary,
    "evidence.schema.json": Evidence,
    "claim.schema.json": Claim,
    "reported-event.schema.json": ReportedEvent,
    "anomaly.schema.json": Anomaly,
    "hypothesis.schema.json": Hypothesis,
    "recommendation.schema.json": Recommendation,
    "confirmed-fault.schema.json": ConfirmedFault,
    "diagnosis-request.schema.json": DiagnosisRequest,
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
        contract_name = filename.removesuffix(".schema.json")
        schema["$id"] = f"{PUBLIC_CONTRACT_ID_PREFIX}:{PUBLIC_CONTRACT_VERSION}:{contract_name}"
        schema["x-contract-version"] = PUBLIC_CONTRACT_VERSION
        if filename == "asset.schema.json":
            schema["x-deprecated-alias-of"] = "drive-system.schema.json"
        (output / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
