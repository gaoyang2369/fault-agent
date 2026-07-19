"""跨模块复用的时区安全时间值对象。"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, model_validator


class TimeRange(BaseModel):
    """表示左闭右开语义的有效时间范围，并统一归一化为 UTC。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_and_normalize(self) -> "TimeRange":
        """校验起止时间带时区且顺序有效，然后转换为 UTC。"""

        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("end must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("start must be before end")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))
        return self
