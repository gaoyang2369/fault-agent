"""Application-level authorization port."""

from typing import Protocol

from modules.asset.domain.models import DriveSystem
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from shared.context import RequestContext
from shared.identifiers import AssetId


class TelemetryAuthorizationPolicy(Protocol):
    def authorize(
        self, command: TelemetryQueryCommand, asset: DriveSystem, context: RequestContext
    ) -> TelemetryQueryCommand: ...


class TelemetryQueryBackend(Protocol):
    def query(
        self,
        *,
        asset_id: AssetId,
        source_locator: object,
        command: TelemetryQueryCommand,
        context: RequestContext,
    ) -> TelemetryQueryResult: ...


class AllowAllTelemetryPolicy:
    """Temporary deterministic policy until Task 5; never reads payload identity."""

    def authorize(
        self, command: TelemetryQueryCommand, asset: DriveSystem, context: RequestContext
    ) -> TelemetryQueryCommand:
        del asset, context
        return command
