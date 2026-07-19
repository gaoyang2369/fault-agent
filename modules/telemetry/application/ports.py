"""遥测应用层的授权与查询后端端口。"""

from typing import Protocol

from modules.asset.domain.models import DriveSystem
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from shared.context import RequestContext
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
