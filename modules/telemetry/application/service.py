"""基于公开资产身份的遥测应用服务。"""

from modules.asset.application.service import AssetSourceResolver
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.ports import (
    DenyAllTelemetryPolicy,
    TelemetryAuthorizationPolicy,
    TelemetryQueryBackend,
)
from modules.telemetry.application.results import TelemetryQueryResult
from shared.context import RequestContext


class TelemetryQueryService:
    """依次解析资产身份、执行授权，再委托基础设施端口查询。"""

    def __init__(
        self,
        resolver: AssetSourceResolver,
        backend: TelemetryQueryBackend,
        *,
        policy: TelemetryAuthorizationPolicy | None = None,
    ) -> None:
        """装配资产解析器、查询后端及可替换的确定性授权策略。"""

        self._resolver = resolver
        self._backend = backend
        self._policy = policy or DenyAllTelemetryPolicy()

    async def query(
        self, command: TelemetryQueryCommand, context: RequestContext
    ) -> TelemetryQueryResult:
        """校验可信上下文并执行资产解析、授权和后端查询完整流程。"""

        context = RequestContext.model_validate(context)
        asset = self._resolver.resolve_asset(
            asset_id=command.asset_id, asset_code=command.asset_code
        )
        authorized = self._policy.authorize(command, asset, context)
        locator = self._resolver.resolve_source(asset.asset_id)
        return self._backend.query(
            asset_id=asset.asset_id,
            source_locator=locator,
            command=authorized,
            context=context,
        )
