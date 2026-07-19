"""遥测应用层的授权与查询后端端口。"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from modules.asset.domain.models import DriveSystem
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from shared.context import RequestContext, Role
from shared.identifiers import AssetId


class TelemetryAuthorizationPolicy(Protocol):
    """定义基于可信请求上下文授权或收紧遥测命令的接口。"""

    def authorize(
        self, command: TelemetryQueryCommand, asset: DriveSystem, context: RequestContext
    ) -> TelemetryQueryCommand:
        """校验调用者对资产和查询范围的权限，并返回授权后的命令。"""
        ...


class TelemetryQueryBackend(Protocol):
    """定义应用服务调用基础设施遥测查询实现的接口。"""

    def query(
        self,
        *,
        asset_id: AssetId,
        source_locator: object,
        command: TelemetryQueryCommand,
        context: RequestContext,
    ) -> TelemetryQueryResult:
        """根据已授权命令和内部源定位读取并返回公开遥测结果。"""
        ...


class AllowAllTelemetryPolicy:
    """Task 5 前的临时确定性放行策略，不读取 payload 自报身份。"""

    def authorize(
        self, command: TelemetryQueryCommand, asset: DriveSystem, context: RequestContext
    ) -> TelemetryQueryCommand:
        """原样返回命令，仅用于尚未接入 IAM 的开发阶段。"""

        del asset, context
        return command


class GuestTelemetryPolicy:
    """在真实 IAM 接入前确定性实施最低游客查询边界。"""

    def __init__(
        self,
        allowed_asset_ids: frozenset[AssetId],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._allowed_asset_ids = allowed_asset_ids
        self._now = now or (lambda: datetime.now(UTC))

    def authorize(
        self, command: TelemetryQueryCommand, asset: DriveSystem, context: RequestContext
    ) -> TelemetryQueryCommand:
        """限制游客为白名单资产、最长一小时且必须聚合的查询。"""

        if Role.GUEST not in context.roles:
            raise PermissionError("guest telemetry policy requires a guest context")
        if asset.asset_id not in self._allowed_asset_ids:
            raise PermissionError("guest access to this asset is not allowed")
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("authorization clock must be timezone-aware")
        if command.time_range.start < now - timedelta(hours=1) or command.time_range.end > now:
            raise PermissionError("guest telemetry queries are limited to the most recent hour")
        if command.aggregation is None:
            raise PermissionError("guest telemetry queries must be aggregated")
        return command
