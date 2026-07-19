"""公开遥测查询命令，禁止包含源表身份和认证信息。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetCode, AssetId
from shared.time import TimeRange


class AggregationFunction(StrEnum):
    """查询支持的确定性数值聚合函数。"""

    MIN = "MIN"
    MAX = "MAX"
    AVG = "AVG"


class AggregationSpec(BaseModel):
    """定义聚合时间窗口和需要计算的聚合函数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    window_seconds: int = Field(gt=0)
    functions: tuple[AggregationFunction, ...] = Field(min_length=1)


class TelemetryQueryCommand(BaseModel):
    """使用公开资产身份、时间范围和信号白名单表达遥测查询。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: AssetId | None = None
    asset_code: AssetCode | None = None
    time_range: TimeRange
    signal_codes: tuple[str, ...] = Field(min_length=1)
    aggregation: AggregationSpec | None = None
    max_points: int = Field(default=10_000, gt=0)

    @model_validator(mode="after")
    def validate_identity_and_signals(self) -> "TelemetryQueryCommand":
        """校验资产 id/编码二选一，并拒绝重复信号。"""

        if (self.asset_id is None) == (self.asset_code is None):
            raise ValueError("exactly one of asset_id or asset_code is required")
        if len(self.signal_codes) != len(set(self.signal_codes)):
            raise ValueError("signal_codes must not contain duplicates")
        return self
