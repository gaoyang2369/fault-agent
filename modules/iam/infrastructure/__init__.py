"""IAM 基础设施适配器。"""

from modules.iam.infrastructure.authentication import (
    AnonymousGuestAuthenticationBackend,
    InMemoryBearerAuthenticationBackend,
)

__all__ = ["AnonymousGuestAuthenticationBackend", "InMemoryBearerAuthenticationBackend"]
