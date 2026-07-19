"""验证仓库内示例可作为可执行 JSON Schema 契约。"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).parents[2]
SCHEMA_DIR = ROOT / "contracts" / "jsonschema"
EXAMPLE_DIR = ROOT / "contracts" / "examples"

EXAMPLE_SCHEMAS = {
    "telemetry-query.valid.json": "telemetry-query-command.schema.json",
    "diagnosis-request.valid.json": "diagnosis-request.schema.json",
    "recommendation.valid.json": "recommendation.schema.json",
    "telemetry-result.acceptable.json": "telemetry-query-result.schema.json",
    "telemetry-result.insufficient.json": "telemetry-query-result.schema.json",
    "diagnosis-result.reported-fault.json": "diagnosis-result.schema.json",
    "diagnosis-result.multiple-hypotheses.json": "diagnosis-result.schema.json",
    "diagnosis-result.insufficient-evidence.json": "diagnosis-result.schema.json",
    "confirmed-fault.valid.json": "confirmed-fault.schema.json",
    "error-response.json": "error-response.schema.json",
}


@pytest.mark.parametrize(("example_name", "schema_name"), EXAMPLE_SCHEMAS.items())
def test_valid_example_matches_schema(example_name: str, schema_name: str) -> None:
    """验证每个公开正例都符合其指定 JSON Schema。"""

    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    example = json.loads((EXAMPLE_DIR / example_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(example)


def test_invalid_example_fails_schema() -> None:
    """验证故意构造的非法查询示例无法通过契约校验。"""

    schema = json.loads(
        (SCHEMA_DIR / "telemetry-query-command.schema.json").read_text(encoding="utf-8")
    )
    example = json.loads((EXAMPLE_DIR / "telemetry-query.invalid.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(example))


def test_public_schemas_do_not_expose_source_locator_or_query_identity() -> None:
    """验证公开 Schema 不暴露源定位信息或不可信查询身份。"""

    schemas = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    )
    assert "device_name" not in schemas
    assert "inverter_name" not in schemas
    command_schema = (SCHEMA_DIR / "telemetry-query-command.schema.json").read_text(
        encoding="utf-8"
    )
    assert "user_id" not in command_schema


def test_public_schema_names_and_versions_are_consistent() -> None:
    """验证公开模型均有规范文件名，且共享同一契约版本元数据。"""

    required = {
        "drive-system.schema.json",
        "component.schema.json",
        "signal-definition.schema.json",
        "time-range.schema.json",
        "observation.schema.json",
        "data-quality-summary.schema.json",
        "reported-event.schema.json",
        "anomaly.schema.json",
        "evidence.schema.json",
        "claim.schema.json",
        "hypothesis.schema.json",
        "recommendation.schema.json",
        "diagnosis-request.schema.json",
        "diagnosis-result.schema.json",
        "error-response.schema.json",
    }
    assert required.issubset({path.name for path in SCHEMA_DIR.glob("*.schema.json")})
    versions = {
        json.loads(path.read_text(encoding="utf-8"))["x-contract-version"]
        for path in SCHEMA_DIR.glob("*.schema.json")
    }
    assert versions == {"1.0.0"}
