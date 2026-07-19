"""无需生产凭据的认证边界适配器与测试夹具。"""

from datetime import UTC, datetime

from modules.iam.application.ports import AuthenticationError
from modules.iam.domain.models import TrustedPrincipal
from shared.context import Role


class AnonymousGuestAuthenticationBackend:
    """开发默认边界：只签发固定游客主体，不信任任何自报身份。"""

    def authenticate(self, authorization: str | None) -> TrustedPrincipal:
        """仅在没有凭据时返回最小权限游客身份。"""

        if authorization is not None:
            raise AuthenticationError("authenticated access is not configured")
        return TrustedPrincipal(
            user_id="anonymous-guest",
            roles=frozenset({Role.GUEST}),
            authenticated_at=datetime.now(UTC),
        )


class InMemoryBearerAuthenticationBackend:
    """供测试和本地组合使用的显式令牌映射，不读取业务 payload。"""

    def __init__(self, principals_by_token: dict[str, TrustedPrincipal]) -> None:
        self._principals_by_token = principals_by_token.copy()

    def authenticate(self, authorization: str | None) -> TrustedPrincipal:
        """严格验证 Bearer 令牌并返回预配置主体。"""

        scheme, separator, token = (authorization or "").partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise AuthenticationError("valid bearer authentication is required")
        principal = self._principals_by_token.get(token)
        if principal is None:
            raise AuthenticationError("invalid bearer authentication")
        return principal
