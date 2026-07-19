"""每次调用都重新取得可信上下文的遥测 Agent tool。"""

from typing import Protocol
from uuid import uuid4

from modules.iam.application.context import RequestContextFactory
from modules.iam.application.ports import AuthenticationBackend
from modules.telemetry.application.commands import TelemetryQueryCommand
from modules.telemetry.application.results import TelemetryQueryResult
from modules.telemetry.application.service import TelemetryQueryService
from shared.context import RequestContext, RequestSource


class AgentToolContextProvider(Protocol):
    """在每次 Tool 调用时重新认证并返回最新授权上下文。"""

    def current_context(self) -> RequestContext:
        """返回本次调用的可信上下文。"""
        ...


class AgentCredentialProvider(Protocol):
    """从 worker 的受信会话边界读取本次调用凭据。"""

    def current_authorization(self) -> str | None:
        """返回当前调用的认证值，不读取 LLM tool 参数。"""
        ...


class ReauthenticatingAgentToolContextProvider:
    """每次调用认证后端，并创建新的 Agent tool 请求上下文。"""

    def __init__(
        self,
        authentication_backend: AuthenticationBackend,
        credential_provider: AgentCredentialProvider,
    ) -> None:
        """保存认证与凭据端口，供每次工具调用重新构造上下文。"""

        self._authentication_backend = authentication_backend
        self._credential_provider = credential_provider
        self._context_factory = RequestContextFactory()

    def current_context(self) -> RequestContext:
        """重新读取和验证凭据，不复用上一次调用的身份或资产范围。"""

        principal = self._authentication_backend.authenticate(
            self._credential_provider.current_authorization()
        )
        return self._context_factory.create(
            principal,
            request_id=str(uuid4()),
            trace_id=str(uuid4()),
            request_source=RequestSource.AGENT_TOOL,
        )


class TelemetryQueryTool:
    """不接受 user_id、role 或 asset_scope 参数的 Agent 遥测工具。"""

    def __init__(
        self,
        service: TelemetryQueryService,
        context_provider: AgentToolContextProvider,
    ) -> None:
        """注入公共遥测应用服务和可信上下文提供器。"""

        self._service = service
        self._context_provider = context_provider

    async def invoke(self, command: TelemetryQueryCommand) -> TelemetryQueryResult:
        """重新认证上下文并复用与 HTTP 相同的应用服务和 IAM 策略。"""

        context = RequestContext.model_validate(self._context_provider.current_context())
        if context.request_source is not RequestSource.AGENT_TOOL:
            raise PermissionError("agent tool requires an AGENT_TOOL request context")
        return await self._service.query(command, context)
