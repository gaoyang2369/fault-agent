"""Read-only profiler for the historical ``real_data`` source.

Run with ``python -m tools.profile_real_data``. The database DSN is read from
``REAL_DATA_DSN`` and is never included in the generated reports.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import unquote, urlsplit

import pymysql
from pymysql.cursors import DictCursor

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type Row = dict[str, Any]

ALLOWED_TABLE = "real_data"
STRING_PROFILE_COLUMNS = (
    "status",
    "fault_code",
    "alarm_code",
    "control_word",
    "status_word",
)
NUMERIC_COLUMNS = (
    "dc_voltage",
    "speed_setpoint",
    "speed_actual",
    "current_actual",
    "torque_setpoint",
    "torque_actual",
    "air_intake_temp",
    "motor_temp",
    "inverter_temp",
    "actual_power",
    "field_current",
    "torque_current",
    "inverter_radiator_temp",
    "inverter_load_rate",
    "motor_load_rate",
    "pulse_frequency",
    "motor_power",
    "feedback_power",
)
SAMPLE_COLUMNS = (
    "id",
    "timestamp",
    "date",
    "time",
    "create_time",
    "device_name",
    "inverter_name",
    *STRING_PROFILE_COLUMNS,
    "system_run_time",
    *NUMERIC_COLUMNS,
)
SELECT_PREFIX = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


@dataclass(frozen=True)
class ConnectionSettings:
    """Validated MySQL connection settings without a printable DSN."""

    host: str
    port: int
    user: str
    password: str
    database: str
    timeout_seconds: int


def parse_mysql_dsn(dsn: str, timeout_seconds: int) -> ConnectionSettings:
    """Parse a MySQL DSN without including credentials in errors."""
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("REAL_DATA_DSN must use mysql:// or mysql+pymysql://")
    database = parsed.path.lstrip("/")
    if not parsed.hostname or parsed.username is None or not database:
        raise ValueError("REAL_DATA_DSN must include host, user, and database")
    if timeout_seconds <= 0:
        raise ValueError("query timeout must be greater than zero")
    return ConnectionSettings(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username),
        password=unquote(parsed.password or ""),
        database=unquote(database),
        timeout_seconds=timeout_seconds,
    )


def validate_select(sql: str) -> None:
    """Reject any statement that is not a single SELECT."""
    if not SELECT_PREFIX.match(sql) or ";" in sql:
        raise ValueError("profiler only permits a single SELECT statement")


class ReadOnlyMySQLClient:
    """Minimal MySQL client that executes only parameterized SELECT queries."""

    def __init__(self, settings: ConnectionSettings) -> None:
        self._connection = pymysql.connect(
            host=settings.host,
            port=settings.port,
            user=settings.user,
            password=settings.password,
            database=settings.database,
            connect_timeout=settings.timeout_seconds,
            read_timeout=settings.timeout_seconds,
            write_timeout=settings.timeout_seconds,
            autocommit=True,
            cursorclass=DictCursor,
        )

    def close(self) -> None:
        self._connection.close()

    def fetch_all(self, sql: str, parameters: Sequence[object] = ()) -> list[Row]:
        validate_select(sql)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cast(list[Row], cursor.fetchall())

    def fetch_one(self, sql: str, parameters: Sequence[object] = ()) -> Row:
        rows = self.fetch_all(sql, parameters)
        if len(rows) != 1:
            raise RuntimeError("expected exactly one profiling result row")
        return rows[0]


class ProfileClient(Protocol):
    """Query surface used by the deterministic profiler."""

    def fetch_all(self, sql: str, parameters: Sequence[object] = ()) -> list[Row]: ...

    def fetch_one(self, sql: str, parameters: Sequence[object] = ()) -> Row: ...


def _parse_datetime_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 13 and text.isdecimal():
        try:
            return datetime.fromtimestamp(int(text) / 1_000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for pattern in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:%S %fms", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def parse_observed_at(row: Mapping[str, object]) -> tuple[datetime | None, str]:
    """Parse the primary timestamp, then fall back to date plus time."""
    primary = _parse_datetime_value(row.get("timestamp"))
    if primary is not None:
        return primary, "timestamp"
    raw_date = row.get("date")
    raw_time = row.get("time")
    if raw_date is None or raw_time is None:
        return None, "failed"
    fallback = _parse_datetime_value(f"{raw_date} {raw_time}")
    if fallback is None:
        return None, "failed"
    return fallback, "date_time"


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, str | int | float | Decimal):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def percentile(sorted_values: Sequence[float], fraction: float) -> float | None:
    """Calculate a linearly interpolated percentile from sorted values."""
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def numeric_statistics(rows: Sequence[Row], columns: Iterable[str]) -> dict[str, JsonValue]:
    """Calculate null rates, descriptive statistics, and percentiles."""
    result: dict[str, JsonValue] = {}
    total = len(rows)
    for column in columns:
        values = sorted(
            number for row in rows if (number := _finite_float(row.get(column))) is not None
        )
        invalid_count = sum(
            row.get(column) is not None and _finite_float(row.get(column)) is None for row in rows
        )
        valid_count = len(values)
        missing_count = total - valid_count
        result[column] = {
            "sample_count": total,
            "valid_count": valid_count,
            "missing_or_invalid_count": missing_count,
            "invalid_non_null_count": invalid_count,
            "null_rate": missing_count / total if total else None,
            "min": values[0] if values else None,
            "max": values[-1] if values else None,
            "mean": statistics.fmean(values) if values else None,
            "stddev_population": statistics.pstdev(values) if values else None,
            "percentiles": {
                "p05": percentile(values, 0.05),
                "p25": percentile(values, 0.25),
                "p50": percentile(values, 0.50),
                "p75": percentile(values, 0.75),
                "p95": percentile(values, 0.95),
            },
            "unit": None,
        }
    return result


def time_parsing_statistics(
    rows: Sequence[Row],
) -> tuple[dict[str, JsonValue], list[datetime | None]]:
    """Profile primary/fallback timestamp parsing without assuming a source timezone."""
    sources: Counter[str] = Counter()
    parsed: list[datetime | None] = []
    for row in rows:
        observed_at, source = parse_observed_at(row)
        parsed.append(observed_at)
        sources[source] += 1
    total = len(rows)
    failed = sources["failed"]
    return (
        {
            "sample_count": total,
            "timestamp_success_count": sources["timestamp"],
            "date_time_fallback_success_count": sources["date_time"],
            "failure_count": failed,
            "failure_rate": failed / total if total else None,
            "source_timezone": None,
            "warning": "TODO-DOMAIN: source timezone is not confirmed",
        },
        parsed,
    )


def interval_statistics(
    rows: Sequence[Row], parsed_times: Sequence[datetime | None]
) -> dict[str, JsonValue]:
    """Calculate observed sampling intervals per device/inverter pair."""
    groups: defaultdict[tuple[str, str], list[datetime]] = defaultdict(list)
    for row, observed_at in zip(rows, parsed_times, strict=True):
        if observed_at is None:
            continue
        if observed_at.tzinfo is not None and observed_at.utcoffset() is not None:
            observed_at = observed_at.astimezone(UTC).replace(tzinfo=None)
        key = (str(row.get("device_name") or ""), str(row.get("inverter_name") or ""))
        groups[key].append(observed_at)
    intervals: list[float] = []
    non_positive_count = 0
    for timestamps in groups.values():
        timestamps.sort()
        for previous, current in pairwise(timestamps):
            seconds = (current - previous).total_seconds()
            if seconds > 0:
                intervals.append(seconds)
            else:
                non_positive_count += 1
    intervals.sort()
    rounded_distribution = Counter(round(value, 3) for value in intervals)
    return {
        "interval_count": len(intervals),
        "non_positive_or_duplicate_count": non_positive_count,
        "min_seconds": intervals[0] if intervals else None,
        "max_seconds": intervals[-1] if intervals else None,
        "mean_seconds": statistics.fmean(intervals) if intervals else None,
        "p50_seconds": percentile(intervals, 0.50),
        "p95_seconds": percentile(intervals, 0.95),
        "most_common_seconds": [
            {"seconds": seconds, "count": count}
            for seconds, count in rounded_distribution.most_common(20)
        ],
    }


def frozen_field_candidates(rows: Sequence[Row], columns: Iterable[str]) -> list[JsonValue]:
    """Report constant fields and longest consecutive equal-value runs as facts."""
    candidates: list[JsonValue] = []
    for column in columns:
        values = [row.get(column) for row in rows]
        non_null = [value for value in values if value is not None]
        if not non_null:
            continue
        distinct_count = len({str(value) for value in non_null})
        longest = 1
        current = 1
        for previous, value in pairwise(non_null):
            current = current + 1 if value == previous else 1
            longest = max(longest, current)
        if distinct_count == 1 or longest > 1:
            candidates.append(
                {
                    "field": column,
                    "non_null_count": len(non_null),
                    "distinct_count": distinct_count,
                    "longest_consecutive_equal_run": longest,
                    "constant_in_sample": distinct_count == 1,
                    "interpretation": "candidate_only_no_fault_inference",
                }
            )
    return candidates


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date | time):
        return value.isoformat()
    return str(value)


def _serialize_rows(rows: Sequence[Row]) -> list[JsonValue]:
    return [{key: _json_value(value) for key, value in row.items()} for row in rows]


def _markdown_cell(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def collect_profile(
    client: ProfileClient,
    *,
    sample_limit: int,
    top_limit: int,
    duplicate_limit: int,
    query_timeout_seconds: int,
) -> dict[str, JsonValue]:
    """Collect full-table aggregates and bounded in-memory sample statistics."""
    summary = client.fetch_one(
        "SELECT COUNT(*) AS row_count, MIN(create_time) AS min_create_time, "
        "MAX(create_time) AS max_create_time FROM `real_data`"
    )
    device_distribution = client.fetch_all(
        "SELECT device_name, inverter_name, COUNT(*) AS row_count, "
        "MIN(create_time) AS min_create_time, MAX(create_time) AS max_create_time "
        "FROM `real_data` GROUP BY device_name, inverter_name "
        "ORDER BY row_count DESC LIMIT %s",
        (top_limit,),
    )
    top_values: dict[str, JsonValue] = {}
    for column in STRING_PROFILE_COLUMNS:
        top_values[column] = _serialize_rows(
            client.fetch_all(
                f"SELECT `{column}` AS value, COUNT(*) AS count FROM `real_data` "
                f"GROUP BY `{column}` ORDER BY count DESC LIMIT %s",
                (top_limit,),
            )
        )
    duplicate_rows = client.fetch_all(
        "SELECT device_name, inverter_name, `timestamp`, COUNT(*) AS duplicate_count "
        "FROM `real_data` GROUP BY device_name, inverter_name, `timestamp` "
        "HAVING COUNT(*) > 1 ORDER BY duplicate_count DESC LIMIT %s",
        (duplicate_limit,),
    )
    selected_columns = ", ".join(f"`{column}`" for column in SAMPLE_COLUMNS)
    sample_rows = client.fetch_all(
        f"SELECT {selected_columns} FROM `real_data` ORDER BY id LIMIT %s", (sample_limit,)
    )
    time_stats, parsed_times = time_parsing_statistics(sample_rows)
    row_count = int(summary.get("row_count") or 0)
    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_table": ALLOWED_TABLE,
            "query_mode": "SELECT_ONLY",
            "query_timeout_seconds": query_timeout_seconds,
            "sample_limit": sample_limit,
            "sample_row_count": len(sample_rows),
            "sample_truncated": row_count > len(sample_rows),
            "credentials_included": False,
        },
        "record_summary": {
            "row_count": row_count,
            "min_create_time": _json_value(summary.get("min_create_time")),
            "max_create_time": _json_value(summary.get("max_create_time")),
        },
        "time_parsing": time_stats,
        "device_inverter_distribution": _serialize_rows(device_distribution),
        "sampling_intervals": interval_statistics(sample_rows, parsed_times),
        "string_top_values": top_values,
        "fault_code_distribution": top_values["fault_code"],
        "alarm_code_distribution": top_values["alarm_code"],
        "numeric_statistics": numeric_statistics(sample_rows, NUMERIC_COLUMNS),
        "duplicate_records": _serialize_rows(duplicate_rows),
        "fixed_or_frozen_candidates": frozen_field_candidates(
            sample_rows, (*STRING_PROFILE_COLUMNS, *NUMERIC_COLUMNS)
        ),
        "warnings": [
            "Numeric units are unknown and intentionally reported as null.",
            "Sample-derived statistics are profiling observations, not industrial thresholds.",
            "Frozen candidates require engineering review and do not establish a fault.",
        ],
    }


def render_markdown(profile: Mapping[str, JsonValue]) -> str:
    """Render all profiling categories as a human-readable Markdown report."""
    metadata = cast(dict[str, JsonValue], profile["metadata"])
    summary = cast(dict[str, JsonValue], profile["record_summary"])
    time_stats = cast(dict[str, JsonValue], profile["time_parsing"])
    intervals = cast(dict[str, JsonValue], profile["sampling_intervals"])
    devices = cast(list[JsonValue], profile["device_inverter_distribution"])
    duplicates = cast(list[JsonValue], profile["duplicate_records"])
    frozen = cast(list[JsonValue], profile["fixed_or_frozen_candidates"])
    top_values = cast(dict[str, JsonValue], profile["string_top_values"])
    numeric = cast(dict[str, JsonValue], profile["numeric_statistics"])
    common_intervals = cast(list[JsonValue], intervals["most_common_seconds"])
    lines = [
        "# real_data 数据摸底报告",
        "",
        "## 范围",
        "",
        f"- 总记录数：{summary['row_count']}",
        f"- 样本记录数：{metadata['sample_row_count']}",
        f"- 样本是否截断：{metadata['sample_truncated']}",
        f"- 最早入库时间：{summary['min_create_time']}",
        f"- 最晚入库时间：{summary['max_create_time']}",
        "- 查询模式：SELECT_ONLY",
        "",
        "## 时间解析",
        "",
        f"- timestamp 成功：{time_stats['timestamp_success_count']}",
        f"- date + time 回退成功：{time_stats['date_time_fallback_success_count']}",
        f"- 失败：{time_stats['failure_count']}",
        f"- 失败率：{time_stats['failure_rate']}",
        "- 源时区：未确认（TODO-DOMAIN）",
        "",
        "## 实际采样间隔",
        "",
        f"- 有效间隔数：{intervals['interval_count']}",
        f"- 最小/平均/最大秒数：{intervals['min_seconds']} / "
        f"{intervals['mean_seconds']} / {intervals['max_seconds']}",
        f"- P50/P95 秒数：{intervals['p50_seconds']} / {intervals['p95_seconds']}",
        "",
        "### 常见采样间隔",
        "",
        "| 秒数 | 次数 |",
        "|---:|---:|",
    ]
    for item_value in common_intervals:
        item = cast(dict[str, JsonValue], item_value)
        lines.append(f"| {_markdown_cell(item['seconds'])} | {_markdown_cell(item['count'])} |")
    lines.extend(
        [
            "",
            "## 设备/变频器分布",
            "",
            "| device_name | inverter_name | 记录数 | 最早入库 | 最晚入库 |",
            "|---|---|---:|---|---|",
        ]
    )
    for item_value in devices:
        item = cast(dict[str, JsonValue], item_value)
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(item.get(key))
                for key in (
                    "device_name",
                    "inverter_name",
                    "row_count",
                    "min_create_time",
                    "max_create_time",
                )
            )
            + " |"
        )
    lines.extend(["", "## 字符串字段 Top 值", ""])
    for field, values_value in top_values.items():
        lines.extend(
            [
                f"### `{field}`",
                "",
                "| 原始值 | 次数 |",
                "|---|---:|",
            ]
        )
        for item_value in cast(list[JsonValue], values_value):
            item = cast(dict[str, JsonValue], item_value)
            lines.append(
                f"| {_markdown_cell(item.get('value'))} | {_markdown_cell(item.get('count'))} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 数值字段统计（基于受限样本）",
            "",
            "未知单位保持为 `null`。",
            "",
            "| 字段 | 有效数 | 缺失/非法率 | min | max | mean | stddev | P05 | P50 | P95 | 单位 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for field, stats_value in numeric.items():
        stats = cast(dict[str, JsonValue], stats_value)
        percentiles = cast(dict[str, JsonValue], stats["percentiles"])
        cells = (
            field,
            stats["valid_count"],
            stats["null_rate"],
            stats["min"],
            stats["max"],
            stats["mean"],
            stats["stddev_population"],
            percentiles["p05"],
            percentiles["p50"],
            percentiles["p95"],
            stats["unit"],
        )
        lines.append("| " + " | ".join(_markdown_cell(value) for value in cells) + " |")
    lines.extend(
        [
            "",
            "## 重复记录候选",
            "",
            "候选键：`(device_name, inverter_name, timestamp)`。",
            "",
            "| device_name | inverter_name | timestamp | 重复数 |",
            "|---|---|---|---:|",
        ]
    )
    if not duplicates:
        lines.append("| _无_ | _无_ | _无_ | 0 |")
    for item_value in duplicates:
        item = cast(dict[str, JsonValue], item_value)
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(item.get(key))
                for key in ("device_name", "inverter_name", "timestamp", "duplicate_count")
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 固定值/冻结候选（基于受限样本）",
            "",
            "| 字段 | 非空数 | 不同值数 | 最长连续相同数 | 样本内固定 | 解释 |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for item_value in frozen:
        item = cast(dict[str, JsonValue], item_value)
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(item.get(key))
                for key in (
                    "field",
                    "non_null_count",
                    "distinct_count",
                    "longest_consecutive_equal_run",
                    "constant_in_sample",
                    "interpretation",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 汇总",
            "",
            f"- 设备/变频器组合数（受 Top 限制）：{len(devices)}",
            f"- 重复候选记录组数（受上限限制）：{len(duplicates)}",
            f"- 固定值/冻结候选字段数：{len(frozen)}",
            "",
            "## 限制",
            "",
            "- 数值单位尚未确认，报告中保持为 null。",
            "- 样本统计不构成工业阈值或故障结论。",
            "- 冻结候选必须由工程师结合运行状态复核。",
            "",
        ]
    )
    return "\n".join(lines)


def _bounded_positive(value: str, *, maximum: int) -> int:
    parsed = int(value)
    if parsed <= 0 or parsed > maximum:
        raise argparse.ArgumentTypeError(f"value must be between 1 and {maximum}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile real_data using SELECT-only queries")
    parser.add_argument(
        "--sample-limit",
        type=lambda value: _bounded_positive(value, maximum=100_000),
        default=int(os.getenv("REAL_DATA_SAMPLE_LIMIT", "10000")),
    )
    parser.add_argument(
        "--top-limit",
        type=lambda value: _bounded_positive(value, maximum=1_000),
        default=100,
    )
    parser.add_argument(
        "--duplicate-limit",
        type=lambda value: _bounded_positive(value, maximum=5_000),
        default=500,
    )
    parser.add_argument("--json-output", type=Path, default=Path("real_data_profile.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("real_data_profile.md"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Connection details remain process-local."""
    args = build_parser().parse_args(argv)
    dsn = os.getenv("REAL_DATA_DSN")
    if not dsn:
        raise SystemExit("REAL_DATA_DSN is required")
    table = os.getenv("REAL_DATA_TABLE", ALLOWED_TABLE)
    if table != ALLOWED_TABLE:
        raise SystemExit("REAL_DATA_TABLE must be real_data")
    timeout_seconds = int(os.getenv("REAL_DATA_QUERY_TIMEOUT_SECONDS", "15"))
    settings = parse_mysql_dsn(dsn, timeout_seconds)
    client = ReadOnlyMySQLClient(settings)
    try:
        profile = collect_profile(
            client,
            sample_limit=args.sample_limit,
            top_limit=args.top_limit,
            duplicate_limit=args.duplicate_limit,
            query_timeout_seconds=timeout_seconds,
        )
    finally:
        client.close()
    args.json_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(profile), encoding="utf-8")
    print(f"JSON report written to {args.json_output}")
    print(f"Markdown report written to {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
