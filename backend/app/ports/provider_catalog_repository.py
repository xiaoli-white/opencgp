from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.provider_catalog import ServerProvider


@runtime_checkable
class ProviderCatalogRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def count(self) -> int:
        ...

    def list_providers(self) -> list[ServerProvider]:
        ...

    def get_provider(self, provider_id: str) -> ServerProvider | None:
        ...

    def save_provider(self, provider: ServerProvider) -> ServerProvider:
        ...

    def delete_provider(self, provider_id: str) -> bool:
        ...

    def clear_default(self, keep_id: str = "") -> None:
        ...
