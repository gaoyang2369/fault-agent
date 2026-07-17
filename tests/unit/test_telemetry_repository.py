"""Unit tests for fixed SQL construction and timestamp normalization."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from modules.telemetry.repository import RealDataRepository, Row


class RecordingExecutor:
    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.sql = ""
        self.parameters: tuple[object, ...] = ()

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        self.sql = sql
        self.parameters = tuple(parameters)
        return self.rows


def test_repository_uses_fixed_parameterized_read_only_query() -> None:
    executor = RecordingExecutor([])
    repository = RealDataRepository(executor, source_timezone="Asia/Shanghai")

    repository.query(
        device_name="motor'; DELETE FROM real_data",
        inverter_name="INV-1",
        start=datetime(2026, 7, 16, tzinfo=UTC),
        end=datetime(2026, 7, 17, tzinfo=UTC),
        signals=("speed_actual",),
    )

    assert executor.sql.startswith("SELECT ")
    assert "DELETE" not in executor.sql
    assert "`speed_actual`" in executor.sql
    assert executor.parameters[:2] == ("motor'; DELETE FROM real_data", "INV-1")


def test_repository_requires_timezone_and_rejects_unknown_signal() -> None:
    with pytest.raises(ValueError, match="must be configured"):
        RealDataRepository(RecordingExecutor([]), source_timezone="")
    repository = RealDataRepository(RecordingExecutor([]), source_timezone="UTC")
    with pytest.raises(ValueError, match="unsupported signals"):
        repository.query(
            device_name="D",
            inverter_name=None,
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 2, tzinfo=UTC),
            signals=("password",),
        )


def test_repository_normalizes_timezone_fallback_and_reports_quality() -> None:
    rows: list[dict[str, Any]] = [
        {
            "id": 1,
            "timestamp": "2026-07-16 08:00:00",
            "date": "2026-07-16",
            "time": "08:00:01",
            "device_name": "D",
            "inverter_name": "I",
            "speed_actual": 10,
        },
        {
            "id": 2,
            "timestamp": "bad",
            "date": "2026/07/16",
            "time": "08:00:03",
            "device_name": "D",
            "inverter_name": "I",
            "speed_actual": 11,
        },
        {"id": 3, "timestamp": "bad", "date": "bad", "time": "bad"},
    ]
    repository = RealDataRepository(RecordingExecutor(rows), source_timezone="Asia/Shanghai")

    result = repository.query(
        device_name="D",
        inverter_name="I",
        start=datetime(2026, 7, 16, tzinfo=UTC),
        end=datetime(2026, 7, 17, tzinfo=UTC),
        signals=("speed_actual",),
    )

    assert [row.observed_at for row in result.rows] == [
        datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
        datetime(2026, 7, 16, 0, 0, 3, tzinfo=UTC),
    ]
    assert {warning.code for warning in result.warnings} == {
        "TIMESTAMP_CONFLICT",
        "TIMESTAMP_PARSE_FAILED",
    }


def test_repository_reports_scan_truncation_and_duplicates() -> None:
    row = {
        "timestamp": "2026-07-16T00:00:00Z",
        "device_name": "D",
        "inverter_name": "I",
        "speed_actual": 1,
    }
    repository = RealDataRepository(
        RecordingExecutor([{**row, "id": 1}, {**row, "id": 2}, {**row, "id": 3}]),
        source_timezone="UTC",
        max_scan_rows=2,
    )
    result = repository.query(
        device_name="D",
        inverter_name="I",
        start=datetime(2026, 7, 15, tzinfo=UTC),
        end=datetime(2026, 7, 17, tzinfo=UTC),
        signals=("speed_actual",),
    )

    assert result.truncated is True
    assert {warning.code for warning in result.warnings} == {
        "DUPLICATE_SOURCE_RECORD",
        "SOURCE_SCAN_TRUNCATED",
    }
