"""Asset-based public telemetry application service."""

from modules.asset.application.service import AssetSourceResolver
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.ports import (
    AllowAllTelemetryPolicy,
    TelemetryAuthorizationPolicy,
    TelemetryQueryBackend,
)
from modules.telemetry.application.results import TelemetryQueryResult
from shared.context import RequestContext


class TelemetryQueryService:
    """Resolve identity, authorize, then delegate through an infrastructure port."""

    def __init__(
        self,
        resolver: AssetSourceResolver,
        backend: TelemetryQueryBackend,
        *,
        policy: TelemetryAuthorizationPolicy | None = None,
    ) -> None:
        self._resolver = resolver
        self._backend = backend
        self._policy = policy or AllowAllTelemetryPolicy()

    async def query(
        self, command: TelemetryQueryCommand, context: RequestContext
    ) -> TelemetryQueryResult:
        context = RequestContext.model_validate(context)
        asset = self._resolver.resolve_asset(
            asset_id=command.asset_id, asset_code=command.asset_code
        )
        locator = self._resolver.resolve_source(asset.asset_id)
        authorized = self._policy.authorize(command, asset, context)
        return self._backend.query(
            asset_id=asset.asset_id,
            source_locator=locator,
            command=authorized,
            context=context,
        )
