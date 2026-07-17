"""Positive and negative tests for Task 4 public contracts."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from modules.asset.domain.models import ComponentType, SignalDataType, SignalDefinition
from modules.diagnosis.domain.models import (
    ConfirmationMethod,
    ConfirmedFault,
    Hypothesis,
    HypothesisTarget,
)
from modules.evidence.domain.models import (
    Claim,
    ClaimGenerator,
    ClaimType,
    EvidenceStatus,
)
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.domain.quality import (
    AllowedAnalysis,
    DataQualityStatus,
    DataQualitySummary,
)
from shared.time import TimeRange


def valid_command() -> dict[str, object]:
    return {
        "asset_code": "G120-1",
        "time_range": {
            "start": "2026-01-14T06:00:00Z",
            "end": "2026-01-14T07:00:00Z",
        },
        "signal_codes": ["speed_actual"],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("device_name", "source-device"),
        ("inverter_name", "source-inverter"),
        ("user_id", "attacker"),
        ("roles", ["ADMIN"]),
        ("raw_sql", "SELECT * FROM real_data"),
    ],
)
def test_public_query_rejects_private_or_identity_fields(field: str, value: object) -> None:
    payload = valid_command()
    payload[field] = value
    with pytest.raises(ValidationError):
        TelemetryQueryCommand.model_validate(payload)


def test_time_range_requires_timezone_and_order_and_normalizes_to_utc() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        TimeRange(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2))
    with pytest.raises(ValidationError, match="before"):
        TimeRange(start=datetime(2026, 1, 2, tzinfo=UTC), end=datetime(2026, 1, 1, tzinfo=UTC))
    value = TimeRange(
        start=datetime(2026, 1, 1, 8, tzinfo=UTC),
        end=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )
    assert value.start.utcoffset() == timedelta(0)


def test_unknown_signal_unit_is_allowed_but_cannot_enable_diagnostics() -> None:
    signal = SignalDefinition(
        signal_code="motor_temp",
        display_name="motor temperature",
        component_type=ComponentType.MOTOR,
        data_type=SignalDataType.FLOAT,
        unit=None,
    )
    assert signal.unit is None
    with pytest.raises(ValidationError, match="confirmed unit"):
        SignalDefinition.model_validate({**signal.model_dump(), "diagnostic_enabled": True})


def test_confirmed_fault_requires_human_identity_and_aware_time() -> None:
    base = {
        "confirmed_fault_id": "confirmed-1",
        "fault_code": "FIELD_CONFIRMED",
        "confirmed_by": "engineer-1",
        "confirmed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "confirmation_method": ConfirmationMethod.INSPECTION,
    }
    ConfirmedFault.model_validate(base)
    for missing in ("confirmed_by", "confirmed_at"):
        invalid = {key: value for key, value in base.items() if key != missing}
        with pytest.raises(ValidationError):
            ConfirmedFault.model_validate(invalid)


def test_material_claim_requires_evidence_or_explicit_insufficient_status() -> None:
    base = {
        "claim_id": "claim-1",
        "claim_type": ClaimType.MATERIAL,
        "statement_code": "CHECK_REQUIRED",
        "generated_by": ClaimGenerator.SYSTEM,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    with pytest.raises(ValidationError, match="requires supporting evidence"):
        Claim.model_validate(base)
    claim = Claim.model_validate({**base, "evidence_status": EvidenceStatus.INSUFFICIENT})
    assert claim.evidence_status is EvidenceStatus.INSUFFICIENT


def test_hypothesis_accepts_multiple_supporting_and_contradicting_evidence() -> None:
    hypothesis = Hypothesis(
        hypothesis_id="hyp-1",
        hypothesis_code="CHECK_TWO_CAUSES",
        target_component=HypothesisTarget.UNKNOWN,
        supporting_evidence_ids=("ev-1", "ev-2"),
        contradicting_evidence_ids=("ev-3", "ev-4"),
    )
    assert len(hypothesis.supporting_evidence_ids) == 2
    assert len(hypothesis.contradicting_evidence_ids) == 2


def test_data_quality_gates_trend_and_duration_analyses() -> None:
    values = {
        "status": DataQualityStatus.INSUFFICIENT,
        "expected_points": 10,
        "observed_points": 1,
        "valid_timestamp_points": 1,
        "completeness": 0.1,
        "timestamp_parse_failure_count": 0,
        "duplicate_count": 0,
        "gap_count": 0,
        "maximum_gap_seconds": None,
        "allowed_analyses": (AllowedAnalysis.POINT_SUMMARY,),
    }
    DataQualitySummary.model_validate(values)
    with pytest.raises(ValidationError, match="cannot enable trend"):
        DataQualitySummary.model_validate(
            {**values, "allowed_analyses": (AllowedAnalysis.TREND_ANALYSIS,)}
        )
