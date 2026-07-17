"""Timezone-safe shared time value objects."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, model_validator


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_and_normalize(self) -> "TimeRange":
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("end must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("start must be before end")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))
        return self
