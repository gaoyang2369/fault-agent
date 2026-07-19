"""在访问基础设施前解析公开资产身份。"""

from modules.asset.application.ports import AssetRepository
from modules.asset.domain.models import DriveSystem
from shared.identifiers import AssetCode, AssetId


class AssetNotFoundError(LookupError):
    """表示资产或资产的数据源映射不存在。"""

    pass


class AssetSourceResolver:
    """把公开资产标识解析为领域资产及其私有数据源定位信息。"""

    def __init__(self, repository: AssetRepository) -> None:
        """使用给定资产仓储初始化解析器。"""

        self._repository = repository

    def resolve_asset(
        self, *, asset_id: AssetId | None, asset_code: AssetCode | None
    ) -> DriveSystem:
        """按互斥的资产 id 或资产编码解析驱动系统，不存在时抛出异常。"""

        asset = (
            self._repository.get_by_id(asset_id)
            if asset_id is not None
            else self._repository.get_by_code(asset_code or "")
        )
        if asset is None:
            raise AssetNotFoundError("asset was not found")
        return asset

    def resolve_source(self, asset_id: AssetId) -> object:
        """解析资产的私有数据源定位对象，不存在时抛出异常。"""

        locator = self._repository.get_source_locator(asset_id)
        if locator is None:
            raise AssetNotFoundError("asset source mapping was not found")
        return locator
