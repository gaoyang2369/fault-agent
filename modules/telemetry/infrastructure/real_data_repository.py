"""只读 ``real_data`` 基础设施适配器。"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from math import ceil
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.asset.infrastructure.models import RealDataSourceLocator
from modules.telemetry.application.commands import (
    AggregationFunction,
    TelemetryQueryCommand,
)
from modules.telemetry.application.results import SourceMetadata, TelemetryQueryResult
from modules.telemetry.domain.models import SignalQuality, SignalValue, TelemetryPoint
from modules.telemetry.domain.quality import (
    AllowedAnalysis,
    DataQualityStatus,
    DataQualitySummary,
)
from shared.context import RequestContext
from shared.identifiers import AssetId

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


class DataQualitySettings(BaseModel):
    """通过运行配置提供数据质量参数，这些值不是工业阈值。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nominal_interval_seconds: float = Field(gt=0)
    gap_warning_seconds: float = Field(gt=0)
    acceptable_completeness: float = Field(ge=0, le=1)
    insufficient_completeness: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> DataQualitySettings:
        """确保数据不足阈值不高于可接受阈值。"""

        if self.insufficient_completeness > self.acceptable_completeness:
            raise ValueError("insufficient_completeness must not exceed acceptable_completeness")
        return self


class QueryExecutor(Protocol):
    """执行固定参数化查询所需的最小数据库接口。"""

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        """执行一条只读查询并返回字典行。"""
        ...


@dataclass(frozen=True, slots=True)
class DataQualityWarning:
    """基础设施内部的数据质量告警。"""

    code: str
    message: str
    source_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedRow:
    """原始源记录及其归一化观测时间。"""

    raw: Row
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryReadResult:
    """仓储读取阶段的内部结果。"""

    rows: tuple[NormalizedRow, ...]
    warnings: tuple[DataQualityWarning, ...]
    scanned_rows: int
    truncated: bool
    discarded_duplicate_count: int
    timestamp_parse_failure_count: int


class RealDataRepository:
    """实现公开遥测查询端口，并把所有源表细节封装在基础设施层。"""

    def __init__(
        self,
        executor: QueryExecutor,
        *,
        source_timezone: str,
        create_time_filter_buffer_seconds: float,
        quality_settings: DataQualitySettings,
        max_scan_rows: int = 100_000,
        max_return_points: int = 10_000,
    ) -> None:
        """校验显式运行配置并装配只读执行器。"""

        if not source_timezone.strip():
            raise ValueError("source_timezone must be configured")
        try:
            self._source_timezone = ZoneInfo(source_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("source_timezone is not a valid IANA timezone") from error
        if create_time_filter_buffer_seconds < 0:
            raise ValueError("create_time_filter_buffer_seconds must not be negative")
        if max_scan_rows <= 0:
            raise ValueError("max_scan_rows must be greater than zero")
        if max_return_points <= 0:
            raise ValueError("max_return_points must be greater than zero")
        self._executor = executor
        self._quality_settings = quality_settings
        self._max_scan_rows = max_scan_rows
        self._max_return_points = max_return_points
        self._create_time_filter_buffer = timedelta(seconds=create_time_filter_buffer_seconds)

    def query(
        self,
        *,
        asset_id: AssetId,
        source_locator: object,
        command: TelemetryQueryCommand,
        context: RequestContext,
    ) -> TelemetryQueryResult:
        """执行已授权的查询并直接返回公开领域结果。"""

        del context
        if not isinstance(source_locator, RealDataSourceLocator):
            raise TypeError("real_data repository requires RealDataSourceLocator")
        read_result = self.read(
            source_locator=source_locator,
            start=command.time_range.start.astimezone(UTC),
            end=command.time_range.end.astimezone(UTC),
            signals=command.signal_codes,
        )
        warnings = list(read_result.warnings)
        if command.aggregation is None:
            points = [
                self._raw_point(row, asset_id, command.signal_codes, warnings)
                for row in read_result.rows
            ]
        else:
            points = self._aggregate(read_result.rows, asset_id, command, warnings)
        maximum = min(command.max_points, self._max_return_points)
        result_truncated = len(points) > maximum
        if result_truncated:
            points = points[:maximum]
            warnings.append(
                DataQualityWarning(
                    code="MAX_POINTS_EXCEEDED",
                    message="result was truncated to the configured maximum point count",
                )
            )
        warning_codes = tuple(warning.code for warning in warnings)
        return TelemetryQueryResult(
            asset_id=asset_id,
            time_range=command.time_range,
            points=tuple(points),
            data_quality=self._summarize_quality(command, read_result, warning_codes),
            warnings=warning_codes,
            source_metadata=SourceMetadata(
                scanned_rows=read_result.scanned_rows,
                matched_rows=len(read_result.rows),
                discarded_duplicate_count=read_result.discarded_duplicate_count,
                truncated=read_result.truncated or result_truncated,
            ),
        )

    def read(
        self,
        *,
        source_locator: RealDataSourceLocator,
        start: datetime,
        end: datetime,
        signals: Sequence[str],
    ) -> RepositoryReadResult:
        """按内部源定位、时间范围和显式信号白名单读取并去重。"""

        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be before end")
        selected_signals = self._validate_signals(signals)
        columns = (*BASE_COLUMNS, *selected_signals)
        sql = f"SELECT {', '.join(f'`{name}`' for name in columns)} FROM `real_data`"
        clauses = ["`device_name` = %s", "`inverter_name` = %s"]
        parameters: list[object] = [source_locator.device_name, source_locator.inverter_name]
        # TODO-DOMAIN: create_time 仅用于配置缓冲后的 SQL 粗筛，observed_at 仍精确复筛。
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
        parse_failures = 0
        for source_row in source_rows:
            observed_at, row_warnings = self._normalize_observed_at(source_row)
            warnings.extend(row_warnings)
            if observed_at is None:
                parse_failures += 1
            elif start <= observed_at < end:
                normalized.append(NormalizedRow(source_row, observed_at))
        groups: dict[tuple[object, object, datetime], list[NormalizedRow]] = {}
        for normalized_row in normalized:
            key = (
                normalized_row.raw.get("device_name"),
                normalized_row.raw.get("inverter_name"),
                normalized_row.observed_at,
            )
            groups.setdefault(key, []).append(normalized_row)
        deduplicated: list[NormalizedRow] = []
        duplicate_count = 0
        for duplicate_rows in groups.values():
            deduplicated.append(max(duplicate_rows, key=self._deduplication_order))
            if len(duplicate_rows) > 1:
                duplicate_count += len(duplicate_rows) - 1
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
        return RepositoryReadResult(
            rows=tuple(deduplicated),
            warnings=tuple(warnings),
            scanned_rows=len(source_rows),
            truncated=truncated,
            discarded_duplicate_count=duplicate_count,
            timestamp_parse_failure_count=parse_failures,
        )

    def _summarize_quality(
        self,
        command: TelemetryQueryCommand,
        read_result: RepositoryReadResult,
        warning_codes: tuple[str, ...],
    ) -> DataQualitySummary:
        """按显式配置计算完整率和间隔，并门控时序分析。"""

        gaps: list[float] = []
        groups: defaultdict[tuple[str | None, str | None], list[NormalizedRow]] = defaultdict(list)
        for row in read_result.rows:
            groups[
                (
                    _optional_text(row.raw.get("device_name")),
                    _optional_text(row.raw.get("inverter_name")),
                )
            ].append(row)
        for rows in groups.values():
            ordered = sorted(rows, key=lambda row: row.observed_at)
            gaps.extend(
                (current.observed_at - previous.observed_at).total_seconds()
                for previous, current in pairwise(ordered)
            )
        duration = (command.time_range.end - command.time_range.start).total_seconds()
        expected_per_series = ceil(duration / self._quality_settings.nominal_interval_seconds)
        expected_points = expected_per_series * max(len(groups), 1)
        observed_points = len(read_result.rows)
        completeness = min(observed_points / expected_points, 1.0) if expected_points else 0.0
        gap_count = sum(gap > self._quality_settings.gap_warning_seconds for gap in gaps)
        if read_result.truncated or completeness < self._quality_settings.insufficient_completeness:
            status = DataQualityStatus.INSUFFICIENT
        elif (
            completeness < self._quality_settings.acceptable_completeness
            or read_result.timestamp_parse_failure_count
            or read_result.discarded_duplicate_count
            or gap_count
        ):
            status = DataQualityStatus.DEGRADED
        else:
            status = DataQualityStatus.ACCEPTABLE
        allowed = [AllowedAnalysis.POINT_SUMMARY, AllowedAnalysis.REPORTED_EVENT_DETECTION]
        if status is not DataQualityStatus.INSUFFICIENT:
            allowed.append(AllowedAnalysis.TREND_ANALYSIS)
            if not gap_count:
                allowed.append(AllowedAnalysis.DURATION_RULES)
        return DataQualitySummary(
            status=status,
            expected_points=expected_points,
            observed_points=observed_points,
            valid_timestamp_points=(observed_points + read_result.discarded_duplicate_count),
            completeness=completeness,
            timestamp_parse_failure_count=read_result.timestamp_parse_failure_count,
            duplicate_count=read_result.discarded_duplicate_count,
            gap_count=gap_count,
            maximum_gap_seconds=max(gaps) if gaps else None,
            allowed_analyses=tuple(allowed),
            warnings=warning_codes,
        )

    @staticmethod
    def _raw_point(
        row: NormalizedRow,
        asset_id: AssetId,
        signals: Sequence[str],
        warnings: list[DataQualityWarning],
    ) -> TelemetryPoint:
        """把一条规范源记录转换为公开遥测点。"""

        values: dict[str, SignalValue] = {}
        record_id = str(row.raw.get("id"))
        for signal in signals:
            value = raw_value(row, signal)
            if signal in NUMERIC_SIGNALS:
                converted = numeric_value(value)
                if value is not None and converted is None:
                    warnings.append(
                        DataQualityWarning(
                            code="INVALID_SIGNAL_VALUE",
                            message=f"{signal} is not a finite numeric value",
                            source_record_ids=(record_id,),
                        )
                    )
                values[signal] = SignalValue(
                    value=converted,
                    unit=None,
                    quality=(
                        SignalQuality.GOOD if converted is not None else SignalQuality.MISSING
                    ),
                )
            else:
                values[signal] = SignalValue(
                    value=None if value is None else str(value),
                    unit=None,
                    quality=(
                        SignalQuality.GOOD if value not in (None, "") else SignalQuality.MISSING
                    ),
                )
        return TelemetryPoint(
            observed_at=row.observed_at,
            asset_id=asset_id,
            source_record_ids=(record_id,),
            values=values,
        )

    def _aggregate(
        self,
        rows: Sequence[NormalizedRow],
        asset_id: AssetId,
        command: TelemetryQueryCommand,
        warnings: list[DataQualityWarning],
    ) -> list[TelemetryPoint]:
        """按固定时间窗口聚合数值信号。"""

        assert command.aggregation is not None
        non_numeric = sorted(set(command.signal_codes) - NUMERIC_SIGNALS)
        if non_numeric:
            raise ValueError(f"aggregation only supports numeric signals: {', '.join(non_numeric)}")
        window = command.aggregation.window_seconds
        start = command.time_range.start.astimezone(UTC)
        buckets: defaultdict[int, list[NormalizedRow]] = defaultdict(list)
        for row in rows:
            bucket = int((row.observed_at - start).total_seconds() // window)
            buckets[bucket].append(row)
        points: list[TelemetryPoint] = []
        for bucket_index, bucket_rows in sorted(buckets.items()):
            values: dict[str, SignalValue] = {}
            for signal in command.signal_codes:
                samples = [
                    value
                    for row in bucket_rows
                    if (value := numeric_value(raw_value(row, signal))) is not None
                ]
                for function in command.aggregation.functions:
                    aggregate = self._apply_aggregate(function, samples)
                    values[f"{signal}.{function.value.lower()}"] = SignalValue(
                        value=aggregate,
                        unit=None,
                        quality=(
                            SignalQuality.GOOD if aggregate is not None else SignalQuality.MISSING
                        ),
                    )
            points.append(
                TelemetryPoint(
                    observed_at=start + timedelta(seconds=bucket_index * window),
                    asset_id=asset_id,
                    source_record_ids=tuple(str(row.raw.get("id")) for row in bucket_rows),
                    values=values,
                )
            )
        if rows and not points:
            warnings.append(
                DataQualityWarning(
                    code="AGGREGATION_EMPTY",
                    message="no valid values were available for aggregation",
                )
            )
        return points

    @staticmethod
    def _apply_aggregate(function: AggregationFunction, samples: Sequence[float]) -> float | None:
        """计算受支持的确定性聚合函数。"""

        if not samples:
            return None
        if function is AggregationFunction.MIN:
            return min(samples)
        if function is AggregationFunction.MAX:
            return max(samples)
        return sum(samples) / len(samples)

    def _to_source_naive(self, value: datetime) -> datetime:
        """把带时区边界时间转换为源时区中的无时区查询参数。"""

        return value.astimezone(self._source_timezone).replace(tzinfo=None)

    def _deduplication_order(self, row: NormalizedRow) -> tuple[datetime, tuple[int, object]]:
        """生成稳定去重排序键，使相同观测优先保留最新源记录。"""

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
        """验证信号白名单并保持调用方给出的顺序。"""

        invalid = sorted(set(signals) - SIGNAL_COLUMNS)
        if invalid:
            raise ValueError(f"unsupported signals: {', '.join(invalid)}")
        if not signals:
            raise ValueError("at least one signal is required")
        return tuple(signals)

    @staticmethod
    def _assert_read_only(sql: str) -> None:
        """拒绝不符合仓储只读约束的 SQL。"""

        if not _SELECT_ONLY.match(sql) or ";" in sql:
            raise ValueError("repository only permits one SELECT statement")

    def _normalize_observed_at(
        self, row: Mapping[str, object]
    ) -> tuple[datetime | None, list[DataQualityWarning]]:
        """解析主时间戳或回退字段，并返回时间质量告警。"""

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
        """组合源日期和时间字段，无法解析时返回空值。"""

        if raw_date is None or raw_time is None:
            return None
        return self._parse_datetime(f"{raw_date} {raw_time}")

    def _parse_datetime(self, value: object) -> datetime | None:
        """兼容源表中的日期时间对象、Unix 毫秒和已知文本格式。"""

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
    """把受支持的源值转换为有限浮点数，未知或非法值保持为空。"""

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
    """读取已通过白名单校验的源信号值。"""

    return cast(object, row.raw.get(signal))


def _optional_text(value: object) -> str | None:
    """把可选源值规范为文本，同时保留真正的空值。"""

    return None if value is None else str(value)
