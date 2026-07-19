"""资产领域模型，本层不包含任何源数据表身份信息。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetCode, AssetId


class StrictModel(BaseModel):
    """拒绝未知字段且实例不可变的资产领域模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AssetType(StrEnum):
    """资产类型枚举。"""

    DRIVE_SYSTEM = "DRIVE_SYSTEM"


class AssetStatus(StrEnum):
    """资产启用状态枚举。"""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ComponentType(StrEnum):
    """驱动系统内可独立识别的组件类型枚举。"""

    INVERTER = "INVERTER"
    MOTOR = "MOTOR"


class SignalDataType(StrEnum):
    """信号在领域契约中的数据类型枚举。"""

    FLOAT = "FLOAT"
    INTEGER = "INTEGER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"


class Component(StrictModel):
    """描述属于某一资产的变频器或电机组件及其已知身份信息。"""

    component_id: str = Field(min_length=1)
    asset_id: AssetId
    component_type: ComponentType
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None


class DriveSystem(StrictModel):
    """描述由独立变频器与电机组成的一套驱动系统资产。"""

    asset_id: AssetId
    asset_code: AssetCode
    display_name: str = Field(min_length=1)
    asset_type: AssetType = AssetType.DRIVE_SYSTEM
    status: AssetStatus
    components: tuple[Component, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_components(self) -> "DriveSystem":
        """校验所有组件归属当前资产，且至少分别包含变频器和电机。"""

        if any(component.asset_id != self.asset_id for component in self.components):
            raise ValueError("every component must belong to the drive system")
        types = {component.component_type for component in self.components}
        if not {ComponentType.INVERTER, ComponentType.MOTOR}.issubset(types):
            raise ValueError("drive system requires separate inverter and motor components")
        return self


class SignalDefinition(StrictModel):
    """定义资产信号的类型、单位、采样周期和诊断启用状态。"""

    signal_code: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    component_type: ComponentType
    data_type: SignalDataType
    unit: str | None = None
    nominal_sampling_interval_seconds: float | None = Field(default=None, gt=0)
    diagnostic_enabled: bool = False

    @model_validator(mode="after")
    def disable_unit_dependent_diagnostics(self) -> "SignalDefinition":
        """禁止在信号单位尚未确认时启用依赖单位的诊断。"""

        if self.unit is None and self.diagnostic_enabled:
            raise ValueError("diagnostic_enabled requires a confirmed unit")
        return self
