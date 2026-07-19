"""验证资产身份到私有数据源定位信息的映射。"""

from modules.asset.application.service import AssetSourceResolver
from modules.asset.infrastructure.in_memory_repository import InMemoryAssetRepository
from modules.asset.infrastructure.models import RealDataSourceLocator


def test_g120_asset_resolves_to_explicit_source_locator() -> None:
    """验证 G120-1 资产可解析到显式且私有的源表定位映射。"""

    repository = InMemoryAssetRepository.g120_fixture()
    resolver = AssetSourceResolver(repository)
    asset = resolver.resolve_asset(asset_id=None, asset_code="G120-1")
    locator = resolver.resolve_source(asset.asset_id)

    assert asset.asset_code == "G120-1"
    assert isinstance(locator, RealDataSourceLocator)
    assert locator.device_name
    assert locator.inverter_name
