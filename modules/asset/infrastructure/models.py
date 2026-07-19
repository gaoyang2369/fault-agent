"""旧数据源使用的私有身份模型。"""

from pydantic import BaseModel, ConfigDict, Field


class RealDataSourceLocator(BaseModel):
    """保存资产在 real_data 表中的设备名与变频器名映射。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_name: str = Field(min_length=1)
    inverter_name: str = Field(min_length=1)
