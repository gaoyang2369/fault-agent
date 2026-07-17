"""Private legacy-source identity model."""

from pydantic import BaseModel, ConfigDict, Field


class RealDataSourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device_name: str = Field(min_length=1)
    inverter_name: str = Field(min_length=1)
