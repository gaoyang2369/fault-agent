"""Stable public error response contract."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    retryable: bool
    trace_id: str = Field(min_length=1)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorDetail
