"""由应用可信边界注入的身份上下文。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from shared.identifiers import UserId


class Role(StrEnum):
    """系统支持的用户角色。"""

    GUEST = "GUEST"
    ENGINEER = "ENGINEER"
    ADMIN = "ADMIN"


class RequestSource(StrEnum):
    """请求进入应用服务的可信来源类型。"""

    HTTP = "HTTP"
    AGENT_TOOL = "AGENT_TOOL"
    INTERNAL = "INTERNAL"


class RequestContext(BaseModel):
    """携带由认证边界确定的请求追踪信息、用户和角色。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: UserId
    roles: frozenset[Role] = Field(min_length=1)
    request_source: RequestSource
