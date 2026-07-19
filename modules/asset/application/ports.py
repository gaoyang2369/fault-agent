"""资产应用层使用的端口协议。"""

from typing import Protocol

from modules.asset.domain.models import DriveSystem, SignalDefinition
from shared.identifiers import AssetCode, AssetId


class AssetRepository(Protocol):
    """抽象资产、私有源定位映射和信号定义的读取接口。"""

    def get_by_id(self, asset_id: AssetId) -> DriveSystem | None:
        """按内部资产标识读取驱动系统，不存在时返回空值。"""
        ...

    def get_by_code(self, asset_code: AssetCode) -> DriveSystem | None:
        """按公开资产编码读取驱动系统，不存在时返回空值。"""
        ...

    def get_source_locator(self, asset_id: AssetId) -> object | None:
        """读取资产对应的私有数据源定位对象，不存在时返回空值。"""
        ...

    def list_signal_definitions(self, asset_id: AssetId) -> tuple[SignalDefinition, ...]:
        """列出指定资产已配置的全部信号定义。"""
        ...
