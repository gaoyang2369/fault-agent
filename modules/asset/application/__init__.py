"""资产模块的应用服务与端口包。"""

from modules.asset.application.ports import AssetRepository
from modules.asset.application.service import AssetSourceResolver

__all__ = ["AssetRepository", "AssetSourceResolver"]
