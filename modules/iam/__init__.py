"""身份与访问管理模块边界。"""

from modules.iam.application import IamAuthorizationPolicy, RequestContextFactory
from modules.iam.domain import IamAction, IamPolicyConfig, TrustedPrincipal

__all__ = [
    "IamAction",
    "IamAuthorizationPolicy",
    "IamPolicyConfig",
    "RequestContextFactory",
    "TrustedPrincipal",
]
