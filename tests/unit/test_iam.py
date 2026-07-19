"""Task 5 可信认证上下文与确定性授权策略测试。"""

import asyncio
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from apps.agent_worker.telemetry_tool import TelemetryQueryTool
from modules.asset.application.service import AssetSourceResolver
from modules.asset.domain.models import DriveSystem
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.iam.application.context import RequestContextFactory
from modules.iam.application.policy import IamAuthorizationPolicy
from modules.iam.domain.models import IamAction, IamPolicyConfig, TrustedPrincipal
from modules.iam.infrastructure.authentication import InMemoryBearerAuthenticationBackend
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.service import TelemetryQueryService
from shared.context import RequestContext, RequestSource, Role

NOW = datetime(2026, 1, 14, 7, tzinfo=UTC)
ASSET = cast(
    DriveSystem,
    InMemoryAssetRepository.g120_fixture().get_by_id("asset-g120-1"),
)


def context(user_id: str, role: Role, source: RequestSource = RequestSource.HTTP) -> RequestContext:
    """构造测试所需的可信上下文。"""

    return RequestContext(
        request_id="request-1",
        trace_id="trace-1",
        user_id=user_id,
        roles=frozenset({role}),
        request_source=source,
    )


def command(**overrides: object) -> TelemetryQueryCommand:
    """构造最近一小时、60 秒聚合的公开查询。"""

    payload: dict[str, object] = {
        "asset_id": "asset-g120-1",
        "time_range": {
            "start": "2026-01-14T06:00:00Z",
            "end": "2026-01-14T07:00:00Z",
        },
        "signal_codes": ["speed_actual"],
        "aggregation": {"window_seconds": 60, "functions": ["AVG"]},
    }
    payload.update(overrides)
    return TelemetryQueryCommand.model_validate(payload)


def policy() -> IamAuthorizationPolicy:
    """构造包含一个游客资产和一个工程师分配的策略。"""

    return IamAuthorizationPolicy(
        IamPolicyConfig(
            guest_visible_asset_ids=frozenset({"asset-g120-1"}),
            engineer_asset_assignments={
                "engineer-1": frozenset({"asset-g120-1"}),
            },
        ),
        now=lambda: NOW,
    )


def test_trusted_authentication_result_constructs_context_and_rejects_spoofed_fields() -> None:
    """验证用户和角色来自认证后端，且可信主体拒绝未知范围字段。"""

    principal = TrustedPrincipal(
        user_id="engineer-1",
        roles=frozenset({Role.ENGINEER}),
        authenticated_at=NOW,
    )
    backend = InMemoryBearerAuthenticationBackend({"opaque-test-token": principal})
    authenticated = backend.authenticate("Bearer opaque-test-token")
    result = RequestContextFactory().create(
        authenticated,
        request_id="request-1",
        trace_id="trace-1",
        request_source=RequestSource.HTTP,
    )

    assert result.user_id == "engineer-1"
    assert result.roles == frozenset({Role.ENGINEER})
    with pytest.raises(ValidationError):
        TrustedPrincipal.model_validate(
            {**principal.model_dump(), "asset_scope": ["asset-attacker-selected"]}
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"aggregation": None},
        {"aggregation": {"window_seconds": 59, "functions": ["AVG"]}},
        {
            "time_range": {
                "start": "2026-01-14T05:59:59Z",
                "end": "2026-01-14T06:59:59Z",
            }
        },
        {
            "time_range": {
                "start": "2026-01-14T06:00:01Z",
                "end": "2026-01-14T07:00:01Z",
            }
        },
        {"signal_codes": ["status_word"]},
    ],
)
def test_guest_cannot_bypass_time_aggregation_or_sensitive_signal_limits(
    overrides: dict[str, object],
) -> None:
    """验证游客最近一小时、聚合粒度和敏感信号边界。"""

    with pytest.raises(PermissionError):
        policy().authorize(command(**overrides), ASSET, context("guest-1", Role.GUEST))


def test_guest_whitelist_engineer_assignments_and_admin_scope() -> None:
    """验证三类角色分别使用白名单、资产分配和全资产上限。"""

    policy().authorize(command(), ASSET, context("guest-1", Role.GUEST))
    policy().authorize(command(aggregation=None), ASSET, context("engineer-1", Role.ENGINEER))
    policy().authorize(command(aggregation=None), ASSET, context("admin-1", Role.ADMIN))

    denied = IamAuthorizationPolicy(IamPolicyConfig(), now=lambda: NOW)
    with pytest.raises(PermissionError, match="guest access"):
        denied.authorize(command(), ASSET, context("guest-1", Role.GUEST))
    with pytest.raises(PermissionError, match="not assigned"):
        policy().authorize(command(), ASSET, context("engineer-2", Role.ENGINEER))


def test_engineer_actions_require_assignment_and_knowledge_requires_admin() -> None:
    """验证诊断/报告资产范围和管理员知识管理能力。"""

    iam = policy()
    engineer = context("engineer-1", Role.ENGINEER)
    iam.authorize_action(IamAction.RUN_DIAGNOSIS, engineer, asset_id="asset-g120-1")
    iam.authorize_action(IamAction.GENERATE_REPORT, engineer, asset_id="asset-g120-1")
    with pytest.raises(PermissionError):
        iam.authorize_action(IamAction.RUN_DIAGNOSIS, engineer, asset_id="asset-other")
    with pytest.raises(PermissionError):
        iam.authorize_action(IamAction.MANAGE_KNOWLEDGE, engineer)
    iam.authorize_action(IamAction.MANAGE_KNOWLEDGE, context("admin-1", Role.ADMIN))


def test_telemetry_service_denies_when_iam_policy_is_not_wired() -> None:
    """验证漏配授权策略时应用服务默认拒绝。"""

    service = TelemetryQueryService(
        AssetSourceResolver(InMemoryAssetRepository.g120_fixture()),
        object(),  # type: ignore[arg-type]
    )
    with pytest.raises(PermissionError, match="not configured"):
        asyncio.run(service.query(command(), context("admin-1", Role.ADMIN)))


def test_agent_tool_reauthorizes_every_invocation() -> None:
    """验证同一 Tool 对象不会缓存上一次调用的高权限上下文。"""

    class Backend:
        def query(self, **_: object) -> object:
            raise RuntimeError("backend reached")

    class ContextProvider:
        calls = 0

        def current_context(self) -> RequestContext:
            self.calls += 1
            role = Role.GUEST if self.calls == 1 else Role.ADMIN
            return context(f"caller-{self.calls}", role, RequestSource.AGENT_TOOL)

    provider = ContextProvider()
    service = TelemetryQueryService(
        AssetSourceResolver(InMemoryAssetRepository.g120_fixture()),
        Backend(),  # type: ignore[arg-type]
        policy=policy(),
    )
    tool = TelemetryQueryTool(service, provider)

    with pytest.raises(PermissionError, match="must be aggregated"):
        asyncio.run(tool.invoke(command(aggregation=None)))
    with pytest.raises(RuntimeError, match="backend reached"):
        asyncio.run(tool.invoke(command(aggregation=None)))
    assert provider.calls == 2
