"""角色、资产、时间和粒度组合授权策略。"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from modules.asset.domain.models import DriveSystem
from modules.iam.domain.models import IamAction, IamPolicyConfig
from modules.telemetry.application.commands import TelemetryQueryCommand
from shared.context import RequestContext, Role
from shared.identifiers import AssetId


class IamAuthorizationPolicy:
    """对 HTTP 与 Agent tool 共用的应用服务执行确定性授权。"""

    def __init__(
        self,
        config: IamPolicyConfig,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """冻结权限配置，并允许测试注入可控的时钟。"""

        self._guest_visible_asset_ids = frozenset(config.guest_visible_asset_ids)
        self._engineer_asset_assignments = {
            user_id: frozenset(asset_ids)
            for user_id, asset_ids in config.engineer_asset_assignments.items()
        }
        self._guest_max_age_seconds = config.guest_max_age_seconds
        self._guest_min_aggregation_window_seconds = config.guest_min_aggregation_window_seconds
        self._guest_restricted_signal_codes = frozenset(config.guest_restricted_signal_codes)
        self._now = now or (lambda: datetime.now(UTC))

    def authorize(
        self, command: TelemetryQueryCommand, asset: DriveSystem, context: RequestContext
    ) -> TelemetryQueryCommand:
        """按最高可信角色校验资产范围，并对游客增加时间和粒度限制。"""

        if Role.ADMIN in context.roles:
            return command
        if Role.ENGINEER in context.roles:
            self._require_engineer_asset(context, asset.asset_id)
            return command
        if Role.GUEST in context.roles:
            self._authorize_guest_telemetry(command, asset.asset_id)
            return command
        raise PermissionError("telemetry access requires an authorized role")

    def authorize_action(
        self,
        action: IamAction,
        context: RequestContext,
        *,
        asset_id: AssetId | None = None,
    ) -> None:
        """授权诊断、报告和知识管理等尚未实现服务的稳定能力边界。"""

        if Role.ADMIN in context.roles:
            return
        if action is IamAction.MANAGE_KNOWLEDGE:
            raise PermissionError("knowledge management requires an administrator")
        if action in {IamAction.RUN_DIAGNOSIS, IamAction.GENERATE_REPORT}:
            if Role.ENGINEER not in context.roles:
                raise PermissionError(f"{action.value} requires an engineer")
            if asset_id is None:
                raise ValueError(f"asset_id is required for {action.value}")
            self._require_engineer_asset(context, asset_id)
            return
        if action is IamAction.QUERY_TELEMETRY:
            raise ValueError("telemetry authorization requires the full query command")
        raise PermissionError("action is not authorized")

    def _require_engineer_asset(self, context: RequestContext, asset_id: AssetId) -> None:
        """确认工程师已被显式分配到目标资产。"""

        assigned = self._engineer_asset_assignments.get(context.user_id, frozenset())
        if asset_id not in assigned:
            raise PermissionError("engineer access to this asset is not assigned")

    def _authorize_guest_telemetry(self, command: TelemetryQueryCommand, asset_id: AssetId) -> None:
        """校验游客的资产、时间、聚合粒度和信号范围。"""

        if asset_id not in self._guest_visible_asset_ids:
            raise PermissionError("guest access to this asset is not allowed")
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("authorization clock must be timezone-aware")
        earliest = now - timedelta(seconds=self._guest_max_age_seconds)
        if command.time_range.start < earliest or command.time_range.end > now:
            raise PermissionError("guest telemetry queries are limited to the most recent hour")
        if command.aggregation is None:
            raise PermissionError("guest telemetry queries must be aggregated")
        if command.aggregation.window_seconds < self._guest_min_aggregation_window_seconds:
            raise PermissionError("guest aggregation window must be at least 60 seconds")
        restricted = set(command.signal_codes) & self._guest_restricted_signal_codes
        if restricted:
            raise PermissionError("guest telemetry query contains restricted signals")
