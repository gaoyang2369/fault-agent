"""与仓储查询逻辑隔离的 PyMySQL 基础设施装配。"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from typing import Any, cast

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from modules.telemetry.infrastructure.real_data_repository import (
    DataQualitySettings,
    RealDataRepository,
    Row,
)
from tools.profile_real_data import parse_mysql_dsn

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


class MySQLQueryExecutor:
    """持有只读数据库会话，并拒绝所有非 SELECT 语句。"""

    def __init__(self, connection: Connection) -> None:
        """保存已建立且应配置为只读的数据库连接。"""

        self._connection = connection

    @classmethod
    def connect(cls, dsn: str, *, timeout_seconds: int) -> MySQLQueryExecutor:
        """解析 DSN，以显式超时和只读事务配置建立 MySQL 会话。"""

        settings = parse_mysql_dsn(dsn, timeout_seconds)
        connection = pymysql.connect(
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
            init_command="SET SESSION TRANSACTION READ ONLY",
        )
        return cls(cast(Connection, connection))

    def fetch_all(self, sql: str, parameters: Sequence[object]) -> list[Row]:
        """防御性校验并执行一条参数化 SELECT，返回全部字典行。"""

        if not _SELECT_ONLY.match(sql) or ";" in sql:
            raise ValueError("telemetry database session only permits one SELECT statement")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cast(list[dict[str, Any]], cursor.fetchall())

    def close(self) -> None:
        """关闭当前持有的数据库连接。"""

        self._connection.close()


def create_repository_from_environment() -> tuple[RealDataRepository, MySQLQueryExecutor]:
    """从环境变量装配仓储，并强制要求显式源时区和安全限制。"""
    dsn = os.getenv("REAL_DATA_DSN")
    if not dsn:
        raise ValueError("REAL_DATA_DSN must be configured")
    source_timezone = os.getenv("SOURCE_TIMEZONE")
    if not source_timezone:
        raise ValueError("SOURCE_TIMEZONE must be configured")
    if os.getenv("REAL_DATA_TABLE", "real_data") != "real_data":
        raise ValueError("REAL_DATA_TABLE must be real_data")
    timeout_seconds = int(os.getenv("REAL_DATA_QUERY_TIMEOUT_SECONDS", "15"))
    max_scan_rows = int(os.getenv("REAL_DATA_MAX_SCAN_ROWS", "100000"))
    max_return_points = int(os.getenv("TELEMETRY_MAX_RETURN_POINTS", "10000"))
    create_time_filter_buffer_seconds = _required_float(
        "REAL_DATA_CREATE_TIME_FILTER_BUFFER_SECONDS"
    )
    quality_settings = _quality_settings_from_environment()
    executor = MySQLQueryExecutor.connect(dsn, timeout_seconds=timeout_seconds)
    try:
        repository = RealDataRepository(
            executor,
            source_timezone=source_timezone,
            create_time_filter_buffer_seconds=create_time_filter_buffer_seconds,
            quality_settings=quality_settings,
            max_scan_rows=max_scan_rows,
            max_return_points=max_return_points,
        )
    except Exception:
        executor.close()
        raise
    return repository, executor


def _quality_settings_from_environment() -> DataQualitySettings:
    """读取显式数据质量配置，缺失时不推断设备行为。"""

    return DataQualitySettings(
        nominal_interval_seconds=_required_float("TELEMETRY_NOMINAL_INTERVAL_SECONDS"),
        gap_warning_seconds=_required_float("TELEMETRY_GAP_WARNING_SECONDS"),
        acceptable_completeness=_required_float("TELEMETRY_ACCEPTABLE_COMPLETENESS"),
        insufficient_completeness=_required_float("TELEMETRY_INSUFFICIENT_COMPLETENESS"),
    )


def _required_float(name: str) -> float:
    """读取必填浮点环境变量，缺失时立即报错而不猜测默认值。"""

    raw_value = os.getenv(name)
    if raw_value is None:
        raise ValueError(f"{name} must be configured")
    return float(raw_value)
