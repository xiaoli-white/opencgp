from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.media import MediaAsset


@runtime_checkable
class MediaRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create(self, asset: MediaAsset) -> MediaAsset:
        ...

    def get(self, asset_id: str, tenant_id: str | None = None) -> MediaAsset | None:
        ...

    def list_assets(
        self, tenant_id: str, kind: str | None = None, limit: int = 50
    ) -> list[MediaAsset]:
        ...

    def delete(self, asset_id: str, tenant_id: str | None = None) -> bool:
        ...
