"""资产模块的基础设施适配器包。"""

from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.asset.infrastructure.models import RealDataSourceLocator

__all__ = ["InMemoryAssetRepository", "RealDataSourceLocator"]
