"""固定 SQL 构造和时间戳归一化的单元测试。"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from modules.asset.infrastructure.models import RealDataSourceLocator
from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)

QUALITY_SETTINGS = DataQualitySettings(
    nominal_interval_seconds=3,
    gap_warning_seconds=9,
    acceptable_completeness=0.95,
    insufficient_completeness=0.8,
)
LOCATOR = RealDataSourceLocator(device_name="D", inverter_name="I")


class RecordingExecutor:
    """记录仓储发出的 SQL 与参数，并返回预设源记录。"""

    def __init__(self, rows: list[Row]) -> None:
        """保存预设源记录并初始化调用记录。"""

        self.rows = rows
        self.sql = ""
        self.parameters: tuple[object, ...] = ()

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        """记录查询文本和参数后返回预设记录。"""

        self.sql = sql
        self.parameters = tuple(parameters)
        return self.rows


def test_repository_uses_fixed_parameterized_read_only_query() -> None:
    """验证仓储仅构造固定、参数化且只读的 SQL。"""

    executor = RecordingExecutor([])
    repository = RealDataRepository(
        executor,
        source_timezone="Asia/Shanghai",
        create_time_filter_buffer_seconds=60,
        quality_settings=QUALITY_SETTINGS,
    )

    repository.read(
        source_locator=RealDataSourceLocator(
            device_name="motor'; DELETE FROM real_data", inverter_name="INV-1"
        ),
        start=datetime(2026, 7, 16, tzinfo=UTC),
        end=datetime(2026, 7, 17, tzinfo=UTC),
        signals=("speed_actual",),
    )

    assert executor.sql.startswith("SELECT ")
    assert "DELETE" not in executor.sql
    assert "`speed_actual`" in executor.sql
    assert "`create_time` >= %s" in executor.sql
    assert "`create_time` < %s" in executor.sql
    assert executor.parameters[:2] == ("motor'; DELETE FROM real_data", "INV-1")


def test_repository_requires_timezone_and_rejects_unknown_signal() -> None:
    """验证仓储强制配置源时区并拒绝非白名单信号。"""

    with pytest.raises(ValueError, match="must be configured"):
        RealDataRepository(
            RecordingExecutor([]),
            source_timezone="",
            create_time_filter_buffer_seconds=0,
            quality_settings=QUALITY_SETTINGS,
        )
    repository = RealDataRepository(
        RecordingExecutor([]),
        source_timezone="UTC",
        create_time_filter_buffer_seconds=0,
        quality_settings=QUALITY_SETTINGS,
    )
    with pytest.raises(ValueError, match="unsupported signals"):
        repository.read(
            source_locator=LOCATOR,
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 2, tzinfo=UTC),
            signals=("password",),
        )


def test_repository_normalizes_timezone_fallback_and_reports_quality() -> None:
    """验证仓储归一化回退时间并报告时间冲突等质量告警。"""

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
    repository = RealDataRepository(
        RecordingExecutor(rows),
        source_timezone="Asia/Shanghai",
        create_time_filter_buffer_seconds=60,
        quality_settings=QUALITY_SETTINGS,
    )

    result = repository.read(
        source_locator=LOCATOR,
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
    """验证仓储报告扫描截断并按稳定规则丢弃重复记录。"""

    row = {
        "timestamp": "2026-07-16T00:00:00Z",
        "device_name": "D",
        "inverter_name": "I",
        "speed_actual": 1,
    }
    repository = RealDataRepository(
        RecordingExecutor([{**row, "id": 1}, {**row, "id": 2}, {**row, "id": 3}]),
        source_timezone="UTC",
        create_time_filter_buffer_seconds=0,
        quality_settings=QUALITY_SETTINGS,
        max_scan_rows=2,
    )
    result = repository.read(
        source_locator=LOCATOR,
        start=datetime(2026, 7, 15, tzinfo=UTC),
        end=datetime(2026, 7, 17, tzinfo=UTC),
        signals=("speed_actual",),
    )

    assert result.truncated is True
    assert result.discarded_duplicate_count == 1
    assert [item.raw["id"] for item in result.rows] == [2]
    assert {warning.code for warning in result.warnings} == {
        "DUPLICATE_SOURCE_RECORD",
        "SOURCE_SCAN_TRUNCATED",
    }


class TimeFilteringExecutor:
    """模拟数据库在 LIMIT 前按 create_time 执行时间粗筛。"""

    def __init__(self, rows: list[Row]) -> None:
        """保存待按查询时间参数筛选的源记录。"""

        self.rows = rows
        self.sql = ""
        self.parameters: tuple[object, ...] = ()

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        """依据仓储传入的粗筛边界返回范围内源记录。"""

        self.sql = sql
        self.parameters = tuple(parameters)
        coarse_start = parameters[-3]
        coarse_end = parameters[-2]
        limit = parameters[-1]
        assert isinstance(coarse_start, datetime)
        assert isinstance(coarse_end, datetime)
        assert isinstance(limit, int)
        return [row for row in self.rows if coarse_start <= row["create_time"] < coarse_end][:limit]


def test_recent_window_is_filtered_in_sql_before_scan_limit() -> None:
    """验证近期时间窗口在扫描上限生效前先由 SQL 粗筛。"""

    old_rows: list[Row] = [
        {
            "id": index,
            "timestamp": f"2020-01-01T00:00:0{index}Z",
            "create_time": datetime(2020, 1, 1, 0, 0, index),
            "device_name": "D",
            "inverter_name": "I",
            "speed_actual": index,
        }
        for index in range(5)
    ]
    recent = {
        "id": 100,
        "timestamp": "2026-07-16T00:00:30Z",
        "create_time": datetime(2026, 7, 16, 0, 0, 31),
        "device_name": "D",
        "inverter_name": "I",
        "speed_actual": 100,
    }
    executor = TimeFilteringExecutor([*old_rows, recent])
    repository = RealDataRepository(
        executor,
        source_timezone="UTC",
        create_time_filter_buffer_seconds=60,
        quality_settings=QUALITY_SETTINGS,
        max_scan_rows=2,
    )

    result = repository.read(
        source_locator=LOCATOR,
        start=datetime(2026, 7, 16, tzinfo=UTC),
        end=datetime(2026, 7, 16, 0, 1, tzinfo=UTC),
        signals=("speed_actual",),
    )

    assert "`create_time` >= %s" in executor.sql
    assert "`create_time` < %s" in executor.sql
    assert executor.parameters[-3:-1] == (
        datetime(2026, 7, 15, 23, 59),
        datetime(2026, 7, 16, 0, 2),
    )
    assert [row.raw["id"] for row in result.rows] == [100]
