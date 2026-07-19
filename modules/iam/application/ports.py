"""可信认证边界端口。"""

from typing import Protocol

from modules.iam.domain.models import TrustedPrincipal


class AuthenticationError(PermissionError):
    """表示认证凭据缺失、格式错误或验证失败。"""


class AuthenticationBackend(Protocol):
    """验证边界凭据并返回可信主体，业务 payload 不参与认证。"""

    def authenticate(self, authorization: str | None) -> TrustedPrincipal:
        """验证完整 Authorization 值，失败时抛出 PermissionError。"""
        ...
