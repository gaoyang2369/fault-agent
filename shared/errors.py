"""稳定的公开错误响应契约。"""

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ErrorDetail(BaseModel):
    """描述机器可读错误码、提示、详情、重试属性和追踪标识。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    retryable: bool
    trace_id: str = Field(min_length=1)


class ErrorResponse(BaseModel):
    """公开 API 的统一错误响应外层对象。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorDetail
