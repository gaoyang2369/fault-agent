"""PyMySQL wiring kept separate from the repository's query logic."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from typing import Any, cast

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from modules.telemetry.repository import RealDataRepository, Row
from modules.telemetry.service import TelemetryQueryService
from tools.profile_real_data import parse_mysql_dsn

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


class MySQLQueryExecutor:
    """Own a read-only DB session and reject every non-SELECT statement."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    @classmethod
    def connect(cls, dsn: str, *, timeout_seconds: int) -> MySQLQueryExecutor:
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
        if not _SELECT_ONLY.match(sql) or ";" in sql:
            raise ValueError("telemetry database session only permits one SELECT statement")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cast(list[dict[str, Any]], cursor.fetchall())

    def close(self) -> None:
        self._connection.close()


def create_repository_from_environment() -> tuple[RealDataRepository, MySQLQueryExecutor]:
    """Create production wiring while requiring an explicit source timezone."""
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
    executor = MySQLQueryExecutor.connect(dsn, timeout_seconds=timeout_seconds)
    return (
        RealDataRepository(
            executor,
            source_timezone=source_timezone,
            max_scan_rows=max_scan_rows,
        ),
        executor,
    )


def create_service_from_environment() -> tuple[TelemetryQueryService, MySQLQueryExecutor]:
    """Create the shared application service with configured safety limits."""
    repository, executor = create_repository_from_environment()
    max_return_points = int(os.getenv("TELEMETRY_MAX_RETURN_POINTS", "10000"))
    return (
        TelemetryQueryService(repository, max_return_points=max_return_points),
        executor,
    )
