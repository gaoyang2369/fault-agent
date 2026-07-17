"""Asset domain models; no source-table identities belong here."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.identifiers import AssetCode, AssetId


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssetType(StrEnum):
    DRIVE_SYSTEM = "DRIVE_SYSTEM"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ComponentType(StrEnum):
    INVERTER = "INVERTER"
    MOTOR = "MOTOR"


class SignalDataType(StrEnum):
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"


class Component(StrictModel):
    component_id: str = Field(min_length=1)
    asset_id: AssetId
    component_type: ComponentType
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None


class DriveSystem(StrictModel):
    asset_id: AssetId
    asset_code: AssetCode
    display_name: str = Field(min_length=1)
    asset_type: AssetType = AssetType.DRIVE_SYSTEM
    status: AssetStatus
    components: tuple[Component, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_components(self) -> "DriveSystem":
        if any(component.asset_id != self.asset_id for component in self.components):
            raise ValueError("every component must belong to the drive system")
        types = {component.component_type for component in self.components}
        if not {ComponentType.INVERTER, ComponentType.MOTOR}.issubset(types):
            raise ValueError("drive system requires separate inverter and motor components")
        return self


class SignalDefinition(StrictModel):
    signal_code: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    component_type: ComponentType
    data_type: SignalDataType
    unit: str | None = None
    nominal_sampling_interval_seconds: float | None = Field(default=None, gt=0)
    diagnostic_enabled: bool = False

    @model_validator(mode="after")
    def disable_unit_dependent_diagnostics(self) -> "SignalDefinition":
        if self.unit is None and self.diagnostic_enabled:
            raise ValueError("diagnostic_enabled requires a confirmed unit")
        return self
