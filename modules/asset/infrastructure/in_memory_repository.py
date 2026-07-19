"""供 M1 开发和测试使用的显式资产及源映射内存实现。"""

from modules.asset.domain.models import (
    AssetStatus,
    Component,
    ComponentType,
    DriveSystem,
    SignalDataType,
    SignalDefinition,
)
from modules.asset.infrastructure.models import RealDataSourceLocator
from shared.identifiers import AssetCode, AssetId


class InMemoryAssetRepository:
    """在进程内保存资产、源定位和信号定义的只读仓储。"""

    def __init__(
        self,
        assets: tuple[DriveSystem, ...],
        locators: dict[str, RealDataSourceLocator],
        signals: dict[str, tuple[SignalDefinition, ...]],
    ) -> None:
        """复制输入集合并建立按资产 id 与编码查询的索引。"""

        self._by_id = {asset.asset_id: asset for asset in assets}
        self._by_code = {asset.asset_code: asset for asset in assets}
        self._locators = locators.copy()
        self._signals = signals.copy()

    @classmethod
    def g120_fixture(cls) -> "InMemoryAssetRepository":
        """创建 G120-1 驱动系统及其当前观测源映射的开发夹具。"""

        asset_id = "asset-g120-1"
        asset = DriveSystem(
            asset_id=asset_id,
            asset_code="G120-1",
            display_name="G120-1 drive system",
            status=AssetStatus.ACTIVE,
            components=(
                Component(
                    component_id="component-g120-1-inverter",
                    asset_id=asset_id,
                    component_type=ComponentType.INVERTER,
                    manufacturer="Siemens",
                    model=None,
                    firmware_version=None,
                ),
                Component(
                    component_id="component-g120-1-motor",
                    asset_id=asset_id,
                    component_type=ComponentType.MOTOR,
                    manufacturer=None,
                    model=None,
                    firmware_version=None,
                ),
            ),
        )
        signals = tuple(
            SignalDefinition(
                signal_code=code,
                display_name=code.replace("_", " "),
                component_type=(
                    ComponentType.MOTOR if code.startswith("motor_") else ComponentType.INVERTER
                ),
                data_type=SignalDataType.FLOAT,
                unit=None,
                nominal_sampling_interval_seconds=3,
                diagnostic_enabled=False,
            )
            for code in ("speed_actual", "motor_temp", "inverter_temp", "motor_load_rate")
        )
        # TODO-DOMAIN: observed names are an explicit fixture mapping, not a confirmed identity.
        locator = RealDataSourceLocator(device_name="G120电机1", inverter_name="G120电机1")
        return cls((asset,), {asset_id: locator}, {asset_id: signals})

    def get_by_id(self, asset_id: AssetId) -> DriveSystem | None:
        """按内部资产标识返回驱动系统。"""

        return self._by_id.get(asset_id)

    def get_by_code(self, asset_code: AssetCode) -> DriveSystem | None:
        """按公开资产编码返回驱动系统。"""

        return self._by_code.get(asset_code)

    def get_source_locator(self, asset_id: AssetId) -> RealDataSourceLocator | None:
        """返回资产对应的私有 real_data 源定位信息。"""

        return self._locators.get(asset_id)

    def list_signal_definitions(self, asset_id: AssetId) -> tuple[SignalDefinition, ...]:
        """返回资产信号定义，未知资产返回空元组。"""

        return self._signals.get(asset_id, ())
