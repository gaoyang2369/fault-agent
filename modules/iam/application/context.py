"""从可信认证结果构造请求上下文。"""

from modules.iam.domain.models import TrustedPrincipal
from shared.context import RequestContext, RequestSource


class RequestContextFactory:
    """只接受认证后端产出的主体和边界生成的追踪标识。"""

    def create(
        self,
        principal: TrustedPrincipal,
        *,
        request_id: str,
        trace_id: str,
        request_source: RequestSource,
    ) -> RequestContext:
        """构造不可由 HTTP/Tool payload 覆盖的可信上下文。"""

        principal = TrustedPrincipal.model_validate(principal)
        return RequestContext(
            request_id=request_id,
            trace_id=trace_id,
            user_id=principal.user_id,
            roles=principal.roles,
            request_source=request_source,
        )
