"""Parsing, statistics, and query-safety tests for the read-only profiler."""

from datetime import UTC, datetime

import pytest

from tools.profile_real_data import (
    frozen_field_candidates,
    interval_statistics,
    numeric_statistics,
    parse_mysql_dsn,
    parse_observed_at,
    percentile,
    time_parsing_statistics,
    validate_select,
)


def test_parse_observed_at_prefers_timestamp() -> None:
    observed_at, source = parse_observed_at(
        {"timestamp": "2026-07-16T08:30:00", "date": "1999-01-01", "time": "00:00:00"}
    )

    assert observed_at == datetime(2026, 7, 16, 8, 30)
    assert source == "timestamp"


def test_parse_observed_at_falls_back_to_date_and_time() -> None:
    observed_at, source = parse_observed_at(
        {"timestamp": "invalid", "date": "2026-07-16", "time": "08:30:00"}
    )

    assert observed_at == datetime(2026, 7, 16, 8, 30)
    assert source == "date_time"


def test_parse_observed_at_supports_observed_epoch_milliseconds_format() -> None:
    observed_at, source = parse_observed_at({"timestamp": "1768371161277"})

    assert observed_at == datetime(2026, 1, 14, 6, 12, 41, 277000, tzinfo=UTC)
    assert source == "timestamp"


def test_parse_observed_at_supports_observed_millisecond_fallback_format() -> None:
    observed_at, source = parse_observed_at(
        {"timestamp": "invalid", "date": "2026/01/14", "time": "14:12:40 998ms"}
    )

    assert observed_at == datetime(2026, 1, 14, 14, 12, 40, 998000)
    assert source == "date_time"


def test_time_parsing_statistics_counts_failures() -> None:
    stats, parsed = time_parsing_statistics(
        [
            {"timestamp": "2026-07-16 00:00:00"},
            {"timestamp": "", "date": "2026-07-16", "time": "00:00:03"},
            {"timestamp": "not-a-time", "date": "bad", "time": "bad"},
        ]
    )

    assert stats["timestamp_success_count"] == 1
    assert stats["date_time_fallback_success_count"] == 1
    assert stats["failure_count"] == 1
    assert stats["failure_rate"] == pytest.approx(1 / 3)
    assert parsed[-1] is None


def test_numeric_statistics_report_nulls_and_percentiles_without_units() -> None:
    stats = numeric_statistics(
        [{"motor_temp": 1}, {"motor_temp": "2"}, {"motor_temp": None}, {"motor_temp": "bad"}],
        ["motor_temp"],
    )["motor_temp"]

    assert isinstance(stats, dict)
    assert stats["valid_count"] == 2
    assert stats["missing_or_invalid_count"] == 2
    assert stats["invalid_non_null_count"] == 1
    assert stats["null_rate"] == 0.5
    assert stats["mean"] == 1.5
    assert stats["unit"] is None
    assert stats["percentiles"] == {
        "p05": 1.05,
        "p25": 1.25,
        "p50": 1.5,
        "p75": 1.75,
        "p95": 1.95,
    }


def test_percentile_handles_empty_and_single_value_samples() -> None:
    assert percentile([], 0.5) is None
    assert percentile([7.0], 0.95) == 7.0


def test_interval_statistics_are_grouped_by_asset_pair() -> None:
    rows = [
        {"device_name": "A", "inverter_name": "I"},
        {"device_name": "A", "inverter_name": "I"},
        {"device_name": "B", "inverter_name": "I"},
    ]
    parsed = [
        datetime(2026, 7, 16, 0, 0, 0),
        datetime(2026, 7, 16, 0, 0, 3),
        datetime(2026, 7, 16, 0, 1, 0),
    ]

    stats = interval_statistics(rows, parsed)

    assert stats["interval_count"] == 1
    assert stats["p50_seconds"] == 3.0


def test_frozen_candidates_report_facts_without_fault_inference() -> None:
    candidates = frozen_field_candidates(
        [{"speed_actual": 10}, {"speed_actual": 10}, {"speed_actual": 12}],
        ["speed_actual"],
    )

    assert candidates == [
        {
            "field": "speed_actual",
            "non_null_count": 3,
            "distinct_count": 2,
            "longest_consecutive_equal_run": 2,
            "constant_in_sample": False,
            "interpretation": "candidate_only_no_fault_inference",
        }
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE real_data SET status = %s",
        "DELETE FROM real_data",
        "SELECT 1; DROP TABLE real_data",
        "INSERT INTO real_data(id) VALUES (%s)",
    ],
)
def test_validate_select_rejects_writes_and_multiple_statements(sql: str) -> None:
    with pytest.raises(ValueError, match="only permits"):
        validate_select(sql)


def test_validate_select_accepts_parameterized_select() -> None:
    validate_select("SELECT * FROM `real_data` WHERE id > %s LIMIT %s")


def test_parse_mysql_dsn_decodes_credentials_without_exposing_them() -> None:
    settings = parse_mysql_dsn("mysql+pymysql://reader:p%40ss@db.local:3307/agent", 12)

    assert settings.host == "db.local"
    assert settings.port == 3307
    assert settings.user == "reader"
    assert settings.password == "p@ss"
    assert settings.database == "agent"
    assert settings.timeout_seconds == 12
