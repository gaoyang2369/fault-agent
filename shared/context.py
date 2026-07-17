"""Trusted identity context injected at an application boundary."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from shared.identifiers import UserId


class Role(StrEnum):
    GUEST = "GUEST"
    ENGINEER = "ENGINEER"
    ADMIN = "ADMIN"


class RequestSource(StrEnum):
    HTTP = "HTTP"
    AGENT_TOOL = "AGENT_TOOL"
    INTERNAL = "INTERNAL"


class RequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: UserId
    roles: frozenset[Role] = Field(min_length=1)
    request_source: RequestSource
