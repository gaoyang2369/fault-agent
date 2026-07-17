"""Read-only adapter for the legacy ``real_data`` wide table."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from modules.telemetry.models import DataQualityWarning

type Row = dict[str, Any]

SIGNAL_COLUMNS = frozenset(
    {
        "status",
        "fault_code",
        "alarm_code",
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
        "system_run_time",
        "inverter_radiator_temp",
        "inverter_load_rate",
        "motor_load_rate",
        "pulse_frequency",
        "motor_power",
        "feedback_power",
    }
)
NUMERIC_SIGNALS = SIGNAL_COLUMNS - {
    "status",
    "fault_code",
    "alarm_code",
    "system_run_time",
}
BASE_COLUMNS = (
    "id",
    "timestamp",
    "date",
    "time",
    "create_time",
    "device_name",
    "inverter_name",
)
_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


class QueryExecutor(Protocol):
    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]: ...


class NormalizedRow:
    def __init__(self, raw: Row, observed_at: datetime) -> None:
        self.raw = raw
        self.observed_at = observed_at


class RepositoryResult:
    def __init__(
        self,
        rows: list[NormalizedRow],
        warnings: list[DataQualityWarning],
        scanned_rows: int,
        truncated: bool,
        discarded_duplicate_count: int,
        timestamp_parse_failure_count: int,
    ) -> None:
        self.rows = rows
        self.warnings = warnings
        self.scanned_rows = scanned_rows
        self.truncated = truncated
        self.discarded_duplicate_count = discarded_duplicate_count
        self.timestamp_parse_failure_count = timestamp_parse_failure_count


class RealDataRepository:
    """Build fixed SELECT statements; callers cannot supply SQL or column names."""

    def __init__(
        self,
        executor: QueryExecutor,
        *,
        source_timezone: str,
        create_time_filter_buffer_seconds: float,
        max_scan_rows: int = 100_000,
    ) -> None:
        if not source_timezone.strip():
            raise ValueError("source_timezone must be configured")
        try:
            self._source_timezone = ZoneInfo(source_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("source_timezone is not a valid IANA timezone") from error
        if max_scan_rows <= 0:
            raise ValueError("max_scan_rows must be greater than zero")
        if create_time_filter_buffer_seconds < 0:
            raise ValueError("create_time_filter_buffer_seconds must not be negative")
        self._executor = executor
        self._max_scan_rows = max_scan_rows
        self._create_time_filter_buffer = timedelta(seconds=create_time_filter_buffer_seconds)

    def query(
        self,
        *,
        device_name: str | None,
        inverter_name: str | None,
        start: datetime,
        end: datetime,
        signals: Sequence[str],
    ) -> RepositoryResult:
        selected_signals = self._validate_signals(signals)
        columns = (*BASE_COLUMNS, *selected_signals)
        sql = f"SELECT {', '.join(f'`{name}`' for name in columns)} FROM `real_data`"
        clauses: list[str] = []
        parameters: list[object] = []
        if device_name is not None:
            clauses.append("`device_name` = %s")
            parameters.append(device_name)
        if inverter_name is not None:
            clauses.append("`inverter_name` = %s")
            parameters.append(inverter_name)
        # TODO-DOMAIN: confirm the formal relationship and maximum lag between
        # create_time (candidate ingestion time) and observed_at. Until then,
        # create_time is only a coarse SQL filter with a configured buffer.
        coarse_start = self._to_source_naive(start - self._create_time_filter_buffer)
        coarse_end = self._to_source_naive(end + self._create_time_filter_buffer)
        clauses.extend(("`create_time` >= %s", "`create_time` < %s"))
        parameters.extend((coarse_start, coarse_end))
        sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY `create_time` ASC, `id` ASC LIMIT %s"
        parameters.append(self._max_scan_rows + 1)
        self._assert_read_only(sql)
        fetched = self._executor.fetch_all(sql, tuple(parameters))
        truncated = len(fetched) > self._max_scan_rows
        source_rows = fetched[: self._max_scan_rows]
        warnings: list[DataQualityWarning] = []
        normalized: list[NormalizedRow] = []
        timestamp_parse_failure_count = 0
        for row in source_rows:
            observed_at, row_warnings = self._normalize_observed_at(row)
            warnings.extend(row_warnings)
            if observed_at is None:
                timestamp_parse_failure_count += 1
            if observed_at is not None and start <= observed_at < end:
                normalized.append(NormalizedRow(row, observed_at))
        duplicate_groups: dict[tuple[object, object, datetime], list[NormalizedRow]] = {}
        for normalized_row in normalized:
            key = (
                normalized_row.raw.get("device_name"),
                normalized_row.raw.get("inverter_name"),
                normalized_row.observed_at,
            )
            duplicate_groups.setdefault(key, []).append(normalized_row)
        deduplicated: list[NormalizedRow] = []
        discarded_duplicate_count = 0
        for duplicate_rows in duplicate_groups.values():
            retained = max(duplicate_rows, key=self._deduplication_order)
            deduplicated.append(retained)
            if len(duplicate_rows) > 1:
                discarded_duplicate_count += len(duplicate_rows) - 1
                warnings.append(
                    DataQualityWarning(
                        code="DUPLICATE_SOURCE_RECORD",
                        message="multiple source rows share the same identity and observed_at",
                        source_record_ids=tuple(str(row.raw.get("id")) for row in duplicate_rows),
                    )
                )
        if truncated:
            warnings.append(
                DataQualityWarning(
                    code="SOURCE_SCAN_TRUNCATED",
                    message="source scan limit reached; the result may be incomplete",
                )
            )
        deduplicated.sort(key=lambda row: row.observed_at)
        return RepositoryResult(
            deduplicated,
            warnings,
            len(source_rows),
            truncated,
            discarded_duplicate_count,
            timestamp_parse_failure_count,
        )

    def _to_source_naive(self, value: datetime) -> datetime:
        return value.astimezone(self._source_timezone).replace(tzinfo=None)

    def _deduplication_order(self, row: NormalizedRow) -> tuple[datetime, tuple[int, object]]:
        create_time = self._parse_datetime(row.raw.get("create_time")) or datetime.min.replace(
            tzinfo=UTC
        )
        raw_id = row.raw.get("id")
        try:
            id_order: tuple[int, object] = (1, int(str(raw_id)))
        except (TypeError, ValueError):
            id_order = (0, str(raw_id or ""))
        return create_time, id_order

    @staticmethod
    def _validate_signals(signals: Sequence[str]) -> tuple[str, ...]:
        invalid = sorted(set(signals) - SIGNAL_COLUMNS)
        if invalid:
            raise ValueError(f"unsupported signals: {', '.join(invalid)}")
        if not signals:
            raise ValueError("at least one signal is required")
        return tuple(signals)

    @staticmethod
    def _assert_read_only(sql: str) -> None:
        if not _SELECT_ONLY.match(sql) or ";" in sql:
            raise ValueError("repository only permits one SELECT statement")

    def _normalize_observed_at(
        self, row: Mapping[str, object]
    ) -> tuple[datetime | None, list[DataQualityWarning]]:
        record_id = str(row.get("id"))
        primary = self._parse_datetime(row.get("timestamp"))
        fallback = self._parse_datetime_parts(row.get("date"), row.get("time"))
        warnings: list[DataQualityWarning] = []
        if primary is not None and fallback is not None and primary != fallback:
            warnings.append(
                DataQualityWarning(
                    code="TIMESTAMP_CONFLICT",
                    message="timestamp and date+time resolve to different instants",
                    source_record_ids=(record_id,),
                )
            )
        observed_at = primary or fallback
        if observed_at is None:
            warnings.append(
                DataQualityWarning(
                    code="TIMESTAMP_PARSE_FAILED",
                    message="neither timestamp nor date+time could be parsed",
                    source_record_ids=(record_id,),
                )
            )
        return observed_at, warnings

    def _parse_datetime_parts(self, raw_date: object, raw_time: object) -> datetime | None:
        if raw_date is None or raw_time is None:
            return None
        return self._parse_datetime(f"{raw_date} {raw_time}")

    def _parse_datetime(self, value: object) -> datetime | None:
        parsed: datetime | None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, time.min)
        elif value is None:
            return None
        else:
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
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                parsed = None
                for pattern in (
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S %fms",
                    "%Y%m%d%H%M%S",
                ):
                    try:
                        parsed = datetime.strptime(text, pattern)
                        break
                    except ValueError:
                        continue
        if parsed is None:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=self._source_timezone)
        return parsed.astimezone(UTC)


def numeric_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, str | int | float | Decimal):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def raw_value(row: NormalizedRow, signal: str) -> object:
    return cast(object, row.raw.get(signal))
