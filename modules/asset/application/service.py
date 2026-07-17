"""Resolve public asset identities before infrastructure access."""

from modules.asset.application.ports import AssetRepository
from modules.asset.domain.models import DriveSystem
from shared.identifiers import AssetCode, AssetId


class AssetNotFoundError(LookupError):
    pass


class AssetSourceResolver:
    def __init__(self, repository: AssetRepository) -> None:
        self._repository = repository

    def resolve_asset(
        self, *, asset_id: AssetId | None, asset_code: AssetCode | None
    ) -> DriveSystem:
        asset = (
            self._repository.get_by_id(asset_id)
            if asset_id is not None
            else self._repository.get_by_code(asset_code or "")
        )
        if asset is None:
            raise AssetNotFoundError("asset was not found")
        return asset

    def resolve_source(self, asset_id: AssetId) -> object:
        locator = self._repository.get_source_locator(asset_id)
        if locator is None:
            raise AssetNotFoundError("asset source mapping was not found")
        return locator
